import json
import os
import sys
import sqlite3
import time
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

INDEX_FIELDS = {
    'id', 'name', 'status', 'modelIndexName', 'serviceId',
    'ownerId', 'resId', 'nativeId', 'clusterId', 'hostId',
    'subnetId', 'portId', 'vmId', 'imageId', 'flavorId',
    'vpcId', 'azoneId', 'podId', 'tenantId',
}


def find_data_dir():
    return os.path.join(SCRIPT_DIR, 'CI+md数据-脱敏-最终-0924')


class DataStore:
    def __init__(self, data_dir):
        self.conn = sqlite3.connect(':memory:', check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self.ci_tables = {}
        self.ci_meta = {}
        self.ci_obj_counts = {}
        self.ci_fields = {}
        self.ci_samples = {}
        self._load_all(data_dir)

    def _load_all(self, data_dir):
        ci_files = {}
        for fname in sorted(os.listdir(data_dir)):
            if not fname.endswith('.json'):
                continue
            name = fname[:-5]
            last_dash = name.rfind('-')
            if last_dash <= 0:
                continue
            ci_name = name[:last_dash]
            page_no = int(name[last_dash + 1:])
            if ci_name not in ci_files:
                ci_files[ci_name] = []
            ci_files[ci_name].append((page_no, os.path.join(data_dir, fname)))

        total_objects = 0
        for ci_name, files in sorted(ci_files.items()):
            files.sort()
            count = self._load_ci(ci_name, files)
            total_objects += count

        return len(ci_files), total_objects

    def _load_ci(self, ci_name, files):
        all_objects = []
        meta = {}

        for _, fpath in files:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not meta:
                meta = {
                    'totalNum': data.get('totalNum', 0),
                    'pageSize': data.get('pageSize', 1000),
                    'totalPageNo': data.get('totalPageNo', 0),
                }
            all_objects.extend(data.get('objList', []))

        self.ci_meta[ci_name] = meta
        self.ci_obj_counts[ci_name] = len(all_objects)

        all_fields = set()
        for obj in all_objects:
            all_fields.update(obj.keys())
        all_fields = sorted(all_fields)

        table = ci_name
        col_defs = [f'"{f}" TEXT' for f in all_fields]
        col_defs.append('"_data" TEXT')
        cols_sql = ', '.join(col_defs)
        self.conn.execute(f'CREATE TABLE "{table}" ({cols_sql})')

        if all_objects:
            col_names = ', '.join(f'"{f}"' for f in all_fields) + ', "_data"'
            placeholders = ', '.join(['?'] * (len(all_fields) + 1))

            rows = []
            for obj in all_objects:
                vals = [self._to_str(obj.get(f, '')) for f in all_fields]
                vals.append(json.dumps(obj, ensure_ascii=False))
                rows.append(vals)

            self.conn.executemany(
                f'INSERT INTO "{table}" ({col_names}) VALUES ({placeholders})',
                rows
            )

        for field in INDEX_FIELDS:
            if field in all_fields:
                idx_name = f'idx_{table}_{field}'
                self.conn.execute(f'CREATE INDEX "{idx_name}" ON "{table}" ("{field}")')

        self.conn.commit()
        self.ci_tables[ci_name] = table
        self.ci_fields[ci_name] = all_fields
        self.ci_samples[ci_name] = all_objects[:3] if all_objects else []
        return len(all_objects)

    @staticmethod
    def _to_str(val):
        if val is None:
            return ''
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    def query(self, ci_name, page_no, page_size, condition_json=None):
        table = self.ci_tables.get(ci_name)
        if table is None:
            return None

        where_clause, params = self._build_where(condition_json)

        with self._lock:
            count_sql = f'SELECT COUNT(*) FROM "{table}"'
            if where_clause:
                count_sql += f' WHERE {where_clause}'
            total_num = self.conn.execute(count_sql, params).fetchone()[0]

            total_page_no = (total_num + page_size - 1) // page_size if page_size > 0 else 0

            if page_no > total_page_no or page_no < 1:
                return {
                    'objList': [],
                    'totalNum': total_num,
                    'pageSize': page_size,
                    'totalPageNo': total_page_no,
                    'currentPage': page_no,
                }

            offset = (page_no - 1) * page_size
            query_sql = f'SELECT "_data" FROM "{table}"'
            if where_clause:
                query_sql += f' WHERE {where_clause}'
            query_sql += ' LIMIT ? OFFSET ?'

            rows = self.conn.execute(query_sql, params + [page_size, offset]).fetchall()

        obj_list = [json.loads(r[0]) for r in rows]

        return {
            'objList': obj_list,
            'totalNum': total_num,
            'pageSize': page_size,
            'totalPageNo': total_page_no,
            'currentPage': page_no,
        }

    def _build_where(self, condition_json):
        if not condition_json:
            return '', []

        try:
            cond = json.loads(condition_json)
        except (json.JSONDecodeError, TypeError):
            return '', []

        constraints = cond.get('constraint', [])
        if not constraints:
            return '', []

        parts = []
        params = []

        for i, c in enumerate(constraints):
            simple = c.get('simple', {})
            name = simple.get('name', '')
            value = simple.get('value')
            operator = simple.get('operator', 'equal')
            log_op = c.get('logOp', 'and')

            if not name:
                continue

            if i > 0:
                parts.append(log_op.upper() if log_op in ('and', 'or') else 'AND')

            if operator == 'equal':
                parts.append(f'"{name}" = ?')
                params.append(self._to_str(value))
            elif operator == 'contain':
                parts.append(f'"{name}" LIKE ?')
                params.append(f'%{self._to_str(value)}%')
            elif operator == 'in':
                if isinstance(value, list) and len(value) > 0:
                    placeholders = ', '.join(['?'] * len(value))
                    parts.append(f'"{name}" IN ({placeholders})')
                    params.extend(self._to_str(v) for v in value)
                else:
                    parts.append('1=0')
            else:
                parts.append('1=1')

        where_clause = ' '.join(parts)
        return where_clause, params

    def get_ci_list(self):
        return sorted(self.ci_tables.keys())

    def get_schema(self, ci_name):
        if ci_name not in self.ci_tables:
            return None
        fields = self.ci_fields.get(ci_name, [])
        samples = self.ci_samples.get(ci_name, [])
        sample_rows = []
        for s in samples[:2]:
            row = {}
            for f in fields:
                v = s.get(f, '')
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, ensure_ascii=False)
                row[f] = v
            sample_rows.append(row)
        return {
            'ci_name': ci_name,
            'columns': fields,
            'row_count': self.ci_obj_counts.get(ci_name, 0),
            'sample_data': sample_rows,
        }

    def get_stats(self):
        return {
            'ci_count': len(self.ci_tables),
            'total_objects': sum(self.ci_obj_counts.values()),
        }


DATA_STORE = None


class DataHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.strip('/')
        qs = parse_qs(parsed.query)

        if path.startswith('rest/hackthon/db/instances/'):
            ci_name = unquote(path[len('rest/hackthon/db/instances/'):])
            self._serve_data(ci_name, qs)
            return

        if path.startswith('rest/hackthon/db/relations/'):
            ci_name = unquote(path[len('rest/hackthon/db/relations/'):])
            self._serve_data(ci_name, qs)
            return

        if path.startswith('rest/hackthon/db/schema/'):
            ci_name = unquote(path[len('rest/hackthon/db/schema/'):])
            self._serve_schema(ci_name)
            return

        self._send_json(404, {'error': 'Not Found', 'path': self.path})

    def _serve_data(self, ci_name, qs):
        try:
            page_no = int(qs.get('pageNo', ['1'])[0])
        except ValueError:
            self._send_json(400, {'error': 'Invalid pageNo'})
            return

        if 'pageSize' in qs:
            try:
                page_size = int(qs['pageSize'][0])
            except ValueError:
                self._send_json(400, {'error': 'Invalid pageSize'})
                return
            if page_size > 10000:
                page_size = 10000
        else:
            page_size = DATA_STORE.ci_meta.get(ci_name, {}).get('pageSize', 1000)

        condition = qs.get('condition', [None])[0]

        try:
            result = DATA_STORE.query(ci_name, page_no, page_size, condition)
        except Exception as e:
            self._send_json(500, {'error': str(e), 'ci': ci_name})
            return

        if result is None:
            self._send_json(404, {
                'error': 'CI not found',
                'ci': ci_name,
            })
            return

        self._send_json(200, result)

    def _send_json(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def _serve_schema(self, ci_name):
        result = DATA_STORE.get_schema(ci_name)
        if result is None:
            self._send_json(404, {'error': 'CI not found', 'ci': ci_name})
            return
        self._send_json(200, result)

    def log_message(self, format, *args):
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), format % args))


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Data Query Service')
    parser.add_argument('--host', default='0.0.0.0', help='Bind host (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8080, help='Listen port (default: 8080)')
    args = parser.parse_args()

    data_dir = find_data_dir()

    if not os.path.isdir(data_dir):
        print(f'ERROR: Data directory not found: {data_dir}')
        sys.exit(1)

    file_count = len([f for f in os.listdir(data_dir) if f.endswith('.json')])

    print(f'\n{"="*60}')
    print(f'  Data Query Service (SQLite In-Memory)')
    print(f'  Data dir: {data_dir} ({file_count} files)')
    print(f'  Loading data into SQLite...')

    t0 = time.time()
    global DATA_STORE
    DATA_STORE = DataStore(data_dir)
    elapsed = time.time() - t0

    stats = DATA_STORE.get_stats()
    print(f'  Loaded: {stats["ci_count"]} tables, {stats["total_objects"]} objects in {elapsed:.1f}s')
    print(f'  Listen:   http://{args.host}:{args.port}')
    print(f'  API:')
    print(f'    GET /rest/hackthon/db/instances/{{CI}}?pageNo=1&pageSize=1000&condition=...')
    print(f'    GET /rest/hackthon/db/relations/{{CI}}?pageNo=1&pageSize=1000&condition=...')
    print(f'{"="*60}\n')

    server = ThreadingHTTPServer((args.host, args.port), DataHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down...')
        server.shutdown()


if __name__ == '__main__':
    main()

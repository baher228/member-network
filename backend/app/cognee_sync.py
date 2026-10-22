import json
from app.cognee_client import sync_network


def main():
    result = sync_network()
    print(json.dumps(result))
    return 1 if result['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Start TownshipFix.

    python run.py              # http://localhost:8000  (resident app)  and /staff
    python run.py --https      # self-signed HTTPS so phones on your Wi-Fi can use camera GPS + voice
    python run.py --port 9000
"""
import argparse
import socket

from app import config, create_app


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--https", action="store_true", help="serve over HTTPS with a temporary certificate")
    args = ap.parse_args()
    scheme = "https" if args.https else "http"
    ip = lan_ip()
    print(f"\n  Resident app : {scheme}://localhost:{args.port}/")
    print(f"  Staff (PIN {config.STAFF_PIN}) : {scheme}://localhost:{args.port}/staff")
    print(f"  On a phone (same Wi-Fi): {scheme}://{ip}:{args.port}/")
    if not args.https:
        print("  Tip: phones only allow voice + GPS on HTTPS -> run with --https\n")
    create_app().run(host="0.0.0.0", port=args.port, ssl_context="adhoc" if args.https else None,
                     debug=False, threaded=True)

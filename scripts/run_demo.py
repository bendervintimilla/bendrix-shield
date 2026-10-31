"""Demo de 3:00 en local (replay): gateway + panel punta a punta.

Uso: ``make demo``. Levanta el gateway y el panel con uvicorn en
puertos libres, corre el guion de ``docs/DEMO.md`` contra HTTP real
(sin red externa ni créditos) y apaga ambos procesos al terminar.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shield.brand import BRAND  # noqa: E402


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_health(client: httpx.Client, url: str, name: str) -> None:
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            if client.get(f"{url}/health").status_code == 200:
                print(f"[ok] {name} en {url}")
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise SystemExit(f"FAIL: {name} no levantó en {url}")


def main() -> int:
    gateway_port, panel_port = _free_port(), _free_port()
    gateway_url = f"http://127.0.0.1:{gateway_port}"
    panel_url = f"http://127.0.0.1:{panel_port}"
    env = {
        **os.environ,
        "DEMO": "replay",
        "SHIELD_VAULT_BACKEND": "memory",
        "SHIELD_SANDBOX": "1",
        "PYTHONPATH": str(ROOT),
    }
    procs = [
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "shield.gateway.app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(gateway_port),
            ],
            cwd=ROOT,
            env=env,
        ),
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "web.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(panel_port),
            ],
            cwd=ROOT,
            env=env,
        ),
    ]
    report = ROOT / "evals" / "report.md"
    snapshot = report.read_bytes() if report.is_file() else None
    try:
        with httpx.Client(timeout=5) as client:
            _wait_health(client, gateway_url, "gateway")
            _wait_health(client, panel_url, "panel")

            print("\n0:00 Black October: las llaves eran el botín (~16 h, USD 310).")
            print("     Con Shield la app nunca tiene la llave real: solo shd_<agente>_…")

            print("\n0:20 Conectar cualquier app en 2 líneas:")
            print("     client = shield.wrap(OpenAI(), 'shd_<agente>_…')  # ver examples/any-app/")
            no_token = client.post(
                f"{gateway_url}/v1/chat/completions",
                json={"model": "muse-spark-1.3", "messages": []},
            )
            assert no_token.status_code == 401, no_token.status_code
            print("[ok] gateway sin token -> 401 (esperado: 401)")

            print("\n0:35 La cuadrilla trabaja (replay, sin créditos):")
            for runner in ("run_invoices.py", "run_stock.py"):
                proc = subprocess.run(
                    [sys.executable, str(ROOT / "evals" / runner)],
                    capture_output=True,
                    text=True,
                    cwd=ROOT,
                )
                assert proc.returncode == 0, proc.stderr[-2000:]
                print(f"[ok] {runner}: {(proc.stdout or '').strip()}")

            print("\n0:55 Factura envenenada y lecturas que piden la credencial:")
            from evals.run_heldout import evaluate

            held = evaluate()
            print(
                f"[ok] held-out: bloqueados {held['blocked']}/{held['poisoned']}, "
                f"ask_owner {held['asked']}, en silencio {held['missed']} "
                f"(antes de H10: 2 en silencio)"
            )
            assert held["missed"] == 0 and held["silent_write_allow"] == 0

            print("\n1:20 País nuevo -> aprobación -> rotación -> atacante 401:")
            page = client.get(f"{panel_url}/")
            assert page.status_code == 200 and BRAND in page.text
            state = client.get(f"{panel_url}/panel/state").json()
            assert 200 in state["attacker_statuses"], state["attacker_statuses"]
            pending = state["pending"]
            assert pending, "el guardián debió dejar una aprobación pendiente"
            approval_id = pending[0]["approval_id"]
            print(
                f"[ok] atacante antes de rotar: {state['attacker_statuses']}; "
                f"aprobación pendiente {approval_id}"
            )
            done = client.post(f"{panel_url}/panel/approve/{approval_id}")
            assert done.status_code == 200, done.status_code
            state = client.get(f"{panel_url}/panel/state").json()
            assert state["attacker_statuses"][-1] == 401, state["attacker_statuses"]
            assert state["executed"], "la rotación debió ejecutarse"
            print(
                f"[ok] atacante después de rotar: {state['attacker_statuses']} "
                f"(200 -> 401); ejecutado: {state['executed']}"
            )

            print("\n2:15 Borrador regulatorio y cero secretos fuera:")
            from shield.notice import draft_both

            drafts = draft_both(summary="demo en replay: token de Bodega rotado")
            assert drafts and all("BORRADOR" in d.render() for d in drafts)
            print(f"[ok] borradores RGPD/LOPDP marcados BORRADOR ({len(drafts)})")

            print("\n2:35 Métricas (evals/report.md, sin inflar):")
            head = (ROOT / "evals" / "report.md").read_text(encoding="utf-8")
            for line in head.splitlines()[5:22]:
                if line.startswith("| H"):
                    print(f"     {line}")
            print("\nDEMO OK: gateway y panel en replay, guion completo en verde.")
            return 0
    finally:
        for proc in procs:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        if snapshot is not None:
            report.write_bytes(snapshot)


if __name__ == "__main__":
    raise SystemExit(main())

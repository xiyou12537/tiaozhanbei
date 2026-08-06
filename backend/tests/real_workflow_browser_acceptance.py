"""Manual real-runtime browser acceptance for molecule workflows.

This intentionally performs no request interception and loads no fixture.  It
requires the real backend, frontend, Docker PySCF image, and Chromium runtime.
Run one molecule at a time, for example: ``--molecule H2``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, sync_playwright


def _sample_working_set(pid: int, stop: threading.Event, samples: list[int]) -> None:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"(Get-Process -Id {pid} -ErrorAction Stop).WorkingSet64",
    ]
    while not stop.is_set():
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode == 0:
            try:
                samples.append(int(completed.stdout.strip()))
            except ValueError:
                pass
        stop.wait(0.5)


def _start_docker_event_capture(docker: str) -> tuple[subprocess.Popen[str], list[str], threading.Thread]:
    process = subprocess.Popen(
        [docker, "events", "--filter", "type=container", "--format", "{{.Action}} {{.Actor.Attributes.image}}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    events: list[str] = []

    def collect() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            events.append(line.strip())

    thread = threading.Thread(target=collect, daemon=True)
    thread.start()
    return process, events, thread


def _stop_process(process: subprocess.Popen[str], thread: threading.Thread) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
    thread.join(timeout=5)


def _register_and_store_session(page: Page) -> dict[str, Any]:
    username = f"real_acceptance_{uuid.uuid4().hex[:16]}"
    response = page.evaluate(
        """async ({ username }) => {
          const response = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password: 'real-runtime-pass-2026' }),
          });
          return { status: response.status, body: await response.json() };
        }""",
        {"username": username},
    )
    if response["status"] != 200:
        raise AssertionError(f"registration failed: {response}")
    payload = response["body"]
    page.evaluate(
        """(payload) => {
          localStorage.setItem('token', payload.token);
          localStorage.setItem('user', JSON.stringify({ id: payload.user_id, username: payload.username }));
        }""",
        payload,
    )
    return payload


def _switch_preset(page: Page, molecule: str) -> None:
    if molecule == "H2":
        return
    radio = page.locator(f"input[type='radio'][value='{molecule}']")
    radio.check(force=True)
    page.wait_for_timeout(150)


def _post_response_predicate(response: Any) -> bool:
    return response.request.method == "POST" and response.url.endswith("/api/molecule-workflows")


def _get_response_predicate(response: Any, workflow_id: str) -> bool:
    return response.request.method == "GET" and response.url.endswith(f"/api/molecule-workflows/{workflow_id}")


def run_acceptance(base_url: str, molecule: str, backend_pid: int, docker: str) -> dict[str, Any]:
    post_requests: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context: BrowserContext = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(20_000)
        page.set_default_navigation_timeout(30_000)

        def record_request(request: Any) -> None:
            if request.method == "POST" and request.url.endswith("/api/molecule-workflows"):
                post_requests.append(
                    {
                        "headers": {key.lower(): value for key, value in request.headers.items()},
                        "post_data": request.post_data_json,
                    }
                )

        page.on("request", record_request)
        page.goto(base_url, wait_until="networkidle")
        auth = _register_and_store_session(page)
        page.goto(f"{base_url}/app/molecules", wait_until="networkidle")
        _switch_preset(page, molecule)

        memory_samples: list[int] = []
        memory_stop = threading.Event()
        memory_thread = threading.Thread(target=_sample_working_set, args=(backend_pid, memory_stop, memory_samples), daemon=True)
        events_process, docker_events, events_thread = _start_docker_event_capture(docker)
        memory_thread.start()
        started = time.perf_counter()
        try:
            with page.expect_response(_post_response_predicate, timeout=600_000) as post_info:
                page.get_by_role("button", name="开始计算").click()
            post_response = post_info.value
            elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
            post_body = post_response.json()
        finally:
            memory_stop.set()
            memory_thread.join(timeout=5)
            _stop_process(events_process, events_thread)

        if post_response.status != 201:
            raise AssertionError(json.dumps({"status": post_response.status, "body": post_body}, ensure_ascii=False))
        workflow_id = post_body["workflow_id"]
        page.wait_for_url(f"**/app/molecule-workflows/{workflow_id}", timeout=30_000)
        with page.expect_response(lambda response: _get_response_predicate(response, workflow_id), timeout=30_000) as refresh_info:
            page.reload(wait_until="domcontentloaded")
        refreshed_body = refresh_info.value.json()

        retry = page.evaluate(
            """async ({ payload, token, idempotencyKey }) => {
              const response = await fetch('/api/molecule-workflows', {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  'Authorization': `Bearer ${token}`,
                  'Idempotency-Key': idempotencyKey,
                },
                body: JSON.stringify(payload),
              });
              return { status: response.status, body: await response.json() };
            }""",
            {
                "payload": post_requests[0]["post_data"],
                "token": auth["token"],
                "idempotencyKey": post_requests[0]["headers"].get("idempotency-key"),
            },
        )
        ui_text = page.locator("body").inner_text()
        browser.close()

    if not post_requests:
        raise AssertionError("the browser did not issue a workflow POST request")
    headers = post_requests[0]["headers"]
    assert headers.get("authorization", "").startswith("Bearer "), "missing Bearer token"
    assert headers.get("idempotency-key"), "missing Idempotency-Key"
    assert retry["status"] == 201 and retry["body"]["workflow_id"] == workflow_id, "idempotency retry created a different workflow"
    assert refreshed_body == post_body, "GET after browser refresh differs from original POST result"
    assert post_body["status"] == "completed"
    expected_validation_status = {"H2": "passed", "LiH": "passed", "H2O": "passed"}[molecule]
    assert post_body["validation_status"] == expected_validation_status
    if expected_validation_status == "needs_review":
        assert post_body["validation_issues"][0]["code"] == "vqe_not_converged"
        assert post_body["validation_issues"][0]["stage"] == "vqe_optimization"
    else:
        assert post_body["validation_issues"] == []
    assert post_body["execution_mode"] == "logical_virtual_qpu"
    assert post_body["is_real_qpu"] is False
    assert {stage["stage"] for stage in post_body["stages"]} == {
        "input_validation", "electronic_structure", "active_space_selection", "fermionic_hamiltonian",
        "qubit_mapping", "vqe_optimization", "circuit_partitioning", "virtual_node_mapping",
        "logical_distributed_simulation",
    }
    assert all(stage["status"] == "completed" for stage in post_body["stages"])
    distribution = post_body["distribution"]
    assert distribution["actual_partition_consumption"] is True
    assert distribution["cross_partition_communication_count"] == len(distribution["communication_events"])
    assert abs(distribution["state_norm"] - 1.0) <= 1e-8
    assert post_body["energies"]["absolute_error_hartree"] <= 1e-8
    assert "虚拟节点逻辑分布式模拟" in ui_text
    assert "非真实 QPU" in ui_text
    assert "QPU 标识异常" not in ui_text

    return {
        "molecule": molecule,
        "workflow_id": workflow_id,
        "post_elapsed_ms": elapsed_ms,
        "backend_peak_working_set_bytes": max(memory_samples, default=None),
        "qubit_count": post_body["hamiltonian"]["qubit_count"],
        "pauli_term_count": post_body["hamiltonian"]["pauli_term_count"],
        "vqe_iterations": post_body["vqe"]["iteration_count"],
        "vqe_converged": post_body["vqe"]["converged"],
        "validation_status": post_body["validation_status"],
        "validation_issues": post_body["validation_issues"],
        "optimizer_diagnostics": post_body["vqe"]["optimizer_diagnostics"],
        "communication_count": distribution["cross_partition_communication_count"],
        "state_norm": distribution["state_norm"],
        "unpartitioned_energy_hartree": post_body["energies"]["unpartitioned_benchmark_energy_hartree"],
        "distributed_energy_hartree": post_body["energies"]["distributed_simulation_energy_hartree"],
        "absolute_error_hartree": post_body["energies"]["absolute_error_hartree"],
        "actual_partition_consumption": distribution["actual_partition_consumption"],
        "docker_qchem_container_events": [event for event in docker_events if "liangzhi-qchem:local" in event],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--molecule", choices=("H2", "LiH", "H2O"), required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--backend-pid", type=int, required=True)
    parser.add_argument("--docker", default=r"C:\Program Files\Docker\Docker\resources\bin\docker.exe")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_acceptance(args.base_url, args.molecule, args.backend_pid, args.docker)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

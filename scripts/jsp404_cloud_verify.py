"""从公开源码执行十一点证明的云端复查，并保存失败或成功的完整证据。"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "submissions/jsp-000404-eleven-point"
EVIDENCE = ROOT / ".work/jsp404-cloud"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_sources():
    manifest = json.loads((PROOF / "verification/source-sha256.json").read_text(encoding="utf-8"))
    for name, expected in manifest.items():
        path = (PROOF / name).resolve()
        if not path.is_relative_to(PROOF.resolve()) or not path.is_file():
            raise RuntimeError(f"源码清单路径无效：{name}")
        if digest(path) != expected["sha256"]:
            raise RuntimeError(f"源码摘要不符：{name}")
    return len(manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    count = check_sources()
    print(f"源码与锁定文件摘要核查通过：{count} 项。", flush=True)
    if args.preflight_only:
        return

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(PYTHONUTF8="1", PYTHONUNBUFFERED="1", LEAN_NUM_THREADS="2",
               MATHLIB_CACHE_DIR=str(PROOF / ".work/cache"))
    results = []
    record = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "platform": platform.platform(), "python": platform.python_version(),
        "source_hashes_checked": count, "repository": os.environ.get("GITHUB_REPOSITORY"),
        "run_id": os.environ.get("GITHUB_RUN_ID"), "results": results,
    }

    def run(name, command, cwd=ROOT):
        print(f"::group::{name}", flush=True)
        start = time.monotonic()
        with (EVIDENCE / f"{name}.log").open("w", encoding="utf-8", newline="\n") as log:
            with subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                  errors="replace") as process:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    print(line, end="", flush=True)
                code = process.wait()
        results.append({"name": name, "exit_code": code, "seconds": time.monotonic() - start})
        print("::endgroup::", flush=True)
        if code:
            raise RuntimeError(f"{name} 失败，退出码 {code}。")

    try:
        run("repository-dependencies", [sys.executable, "-m", "pip", "install",
                                       "--disable-pip-version-check", "-r", "requirements.txt"])
        for task in ("validate", "links", "build", "check"):
            run(f"repository-{task}", [sys.executable, "scripts/manage.py", task])
        run("repository-history", [sys.executable, "scripts/manage.py", "history", "--base",
                                   "f4e7173d89dfe91022a185427d63452c8ffbf6ae"])
        run("repository-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])

        lake = shutil.which("lake", path=env["PATH"])
        if not lake:
            raise RuntimeError("找不到固定版本的 Lake。")
        # 只准备实际导入的 Mathlib 模块及其依赖缓存。
        imports = set()
        sources = list(PROOF.glob("*.lean")) + list((PROOF / "SunPrize").rglob("*.lean"))
        sources += list((PROOF / "vendor").rglob("*.lean"))
        for source in sources:
            imports.update(re.findall(r"^import\s+(Mathlib(?:\.[A-Za-z0-9_]+)*)\s*$",
                                      source.read_text(encoding="utf-8"), re.MULTILINE))
        if not imports:
            raise RuntimeError("未找到 Mathlib 导入，拒绝继续。")
        run("mathlib-cache", [lake, "exe", "cache", "get", *sorted(imports)], PROOF)
        lock = json.loads((PROOF / "lake-manifest.json").read_text(encoding="utf-8"))
        dependencies = []
        for package in lock["packages"]:
            path = PROOF / ".lake/packages" / package["name"]
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()
            dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"],
                                            cwd=path, text=True).strip()
            if head != package["rev"] or dirty:
                raise RuntimeError(f"依赖版本或源码状态不符：{package['name']}")
            dependencies.append({"name": package["name"], "commit": head})
        record["dependencies"] = dependencies
        run("lean-complete-verification", [sys.executable, "-u", "scripts/verify_project.py"], PROOF)
        audit = json.loads((PROOF / ".work/verification/audit-result.json").read_text(encoding="utf-8"))
        if audit["exit_code"] != 0 or audit["trust"] != 0:
            raise RuntimeError("最终审计记录无效。")
        record["audit"] = audit
        record["status"] = "passed"
    except Exception as error:
        record["status"] = "failed"
        record["error"] = str(error)
        raise
    finally:
        record["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        evidence = PROOF / ".work/verification"
        if evidence.exists():
            shutil.copytree(evidence, EVIDENCE / "lean", dirs_exist_ok=True)
        (EVIDENCE / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8", newline="\n")
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as output:
                output.write(f"## 十一点证明云端核验\n\n状态：`{record['status']}`\n\n")
                output.write(f"提交：`{record['commit']}`\n\n源码摘要核查：{count} 项。\n\n")
                output.write("完整记录位于本次运行的 `jsp404-verification` 附件。\n")
                if record["status"] == "passed":
                    output.write("\n全部证明模块重新编译及最终 `--trust=0` 审计通过。\n")


if __name__ == "__main__":
    main()

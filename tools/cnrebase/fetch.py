"""从 CurseForge 拉取整合包（客户端 + 官方服务端包）。

CI 里只需要传一个版本号即可自动取包，也支持直接给 URL 绕过 API
（部分作者禁用了第三方下载，``downloadUrl`` 会返回 null）。

用法::

    python -m tools.cnrebase.fetch --version 0.34.1 --out work/packs
    python -m tools.cnrebase.fetch --version 0.34.1 --out work/packs \\
        --url-client https://... --url-server https://...

stdout 会打印一行 JSON，便于 workflow 用 ``jq`` 取路径。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.curseforge.com/v1"
CDN = "https://edge.forgecdn.net/files"
CDN_ALT = "https://mediafilez.forgecdn.net/files"

#: Wold's Vaults - Vault Hunters Expansion
DEFAULT_PROJECT = 957311


def _api(path: str, key: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        API + path,
        headers={"x-api-key": key, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def cdn_url(f: dict, alt: bool = False) -> str:
    """取可下载直链；作者关闭 API 下载时按 fileId 规则推导 CDN 地址。"""
    u = f.get("downloadUrl")
    if u:
        return u
    fid = int(f["id"])
    base = CDN_ALT if alt else CDN
    return f"{base}/{fid // 1000}/{fid % 1000}/{f['fileName']}"


def list_files(project_id: int, key: str, page_size: int = 50) -> list[dict]:
    data = _api(f"/mods/{project_id}/files?pageSize={page_size}", key)
    return data.get("data") or []


def pick_release(files: list[dict], version: str) -> dict:
    """按版本号挑主包（排除服务端包）。"""
    mains = [f for f in files if not f.get("isServerPack")]
    exact = [f for f in mains if version in (f.get("fileName") or "")]
    if not exact:
        names = ", ".join(f.get("fileName", "?") for f in mains[:8])
        raise LookupError(f"未找到版本 {version} 的主包。可用: {names}")
    # 同名多个时取 fileDate 最新的
    exact.sort(key=lambda f: f.get("fileDate") or "", reverse=True)
    return exact[0]


def pick_server_pack(files: list[dict], main: dict, version: str, key: str) -> dict | None:
    """定位官方服务端包。优先用主包的 serverPackFileId，其次按 isServerPack 匹配。"""
    sp_id = main.get("serverPackFileId")
    if sp_id:
        try:
            return _api(f"/mods/{main['id']}/files/{sp_id}", key)["data"]
        except urllib.error.HTTPError:
            pass
    cands = [
        f
        for f in files
        if f.get("isServerPack") and version.replace(".", "-") in (f.get("fileName") or "").replace(".", "-")
    ]
    if not cands:
        cands = [f for f in files if f.get("isServerPack")]
    if not cands:
        return None
    cands.sort(key=lambda f: f.get("fileDate") or "", reverse=True)
    return cands[0]


def download(url: str, dest: Path, quiet: bool = False) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "cnrebase/1.0"})
    with urllib.request.urlopen(req, timeout=600) as r, dest.open("wb") as fh:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        mark = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if not quiet and total and done - mark >= (1 << 22):
                mark = done
                print(
                    f"    {dest.name}: {done / 1048576:.0f}/{total / 1048576:.0f} MB",
                    file=sys.stderr,
                )
    if not quiet:
        print(f"    完成 {dest.name} ({dest.stat().st_size / 1048576:.1f} MB)", file=sys.stderr)
    return dest


def fetch(
    version: str,
    out_dir: Path,
    project_id: int = DEFAULT_PROJECT,
    api_key: str = "",
    url_client: str = "",
    url_server: str = "",
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict = {"version": version, "client": None, "server": None}

    if url_client:
        dest = out_dir / f"client-{version}.zip"
        if dest.is_file():
            print(f"[skip] {dest.name} 已存在", file=sys.stderr)
        else:
            download(url_client, dest)
        result["client"] = str(dest)
    if url_server:
        dest = out_dir / f"server-{version}.zip"
        if dest.is_file():
            print(f"[skip] {dest.name} 已存在", file=sys.stderr)
        else:
            download(url_server, dest)
        result["server"] = str(dest)

    if result["client"] and result["server"]:
        return result
    if not api_key:
        raise SystemExit(
            "缺少 CurseForge API key，且未提供完整 URL。"
            "请设置 CF_API_KEY，或用 --url-client/--url-server 指定直链。"
        )

    files = list_files(project_id, api_key)
    main = pick_release(files, version)
    result["mainFileId"] = main["id"]
    result["mainFileName"] = main.get("fileName")

    if not result["client"]:
        dest = out_dir / (main.get("fileName") or f"client-{version}.zip")
        if dest.is_file():
            print(f"[skip] {dest.name} 已存在", file=sys.stderr)
        else:
            try:
                download(cdn_url(main), dest)
            except urllib.error.HTTPError:
                download(cdn_url(main, alt=True), dest)
        result["client"] = str(dest)

    if not result["server"]:
        sp = pick_server_pack(files, main, version, api_key)
        if sp is None:
            print("[warn] 未找到官方服务端包，将只构建客户端产物", file=sys.stderr)
        else:
            dest = out_dir / (sp.get("fileName") or f"server-{version}.zip")
            if dest.is_file():
                print(f"[skip] {dest.name} 已存在", file=sys.stderr)
            else:
                try:
                    download(cdn_url(sp), dest)
                except urllib.error.HTTPError:
                    download(cdn_url(sp, alt=True), dest)
            result["server"] = str(dest)
            result["serverFileId"] = sp["id"]
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cnrebase.fetch", description="拉取 Wold's Vaults 整合包")
    p.add_argument("--version", required=True, help="整合包版本，如 0.34.1")
    p.add_argument("--out", default="work/packs", help="下载目录")
    p.add_argument("--project", type=int, default=DEFAULT_PROJECT, help="CurseForge projectID")
    p.add_argument("--api-key", default="", help="CurseForge API key（默认读 CF_API_KEY）")
    p.add_argument("--url-client", default="", help="客户端整合包直链（跳过 API）")
    p.add_argument("--url-server", default="", help="服务端包直链（跳过 API）")
    args = p.parse_args(argv)

    key = args.api_key or __import__("os").environ.get("CF_API_KEY", "")
    res = fetch(
        version=args.version,
        out_dir=Path(args.out),
        project_id=args.project,
        api_key=key,
        url_client=args.url_client,
        url_server=args.url_server,
    )
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

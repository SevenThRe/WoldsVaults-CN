# -*- coding: utf-8 -*-
"""1006j: 核对 CN jar 的 mixin 注册清单，找死代码"""
import zipfile, json

P = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar"
z = zipfile.ZipFile(P)
names = z.namelist()
cfgs = [n for n in names if n.endswith(".json") and "mixin" in n.lower()]
print("mixin 配置文件:", cfgs)
registered = set()
for c in cfgs:
    try:
        d = json.loads(z.read(c).decode("utf-8"))
    except Exception as e:
        print(c, "ERR", e)
        continue
    for sec in ("mixins", "client", "server"):
        if sec in d:
            print(f"  {c} [{sec}] {len(d[sec])}")
            for m in d[sec]:
                print("     ", m)
                registered.add(m.rsplit(".", 1)[-1])
cls = [n for n in names if n.endswith(".class")]
print()
print("jar 内 class 总数:", len(cls))
mx = sorted(n.rsplit("/", 1)[-1][:-6] for n in cls if "Mixin" in n or "mixin" in n)
print("jar 内含 Mixin 的 class:", mx)
print()
print("!!! 有 class 但未被任何 mixin json 引用（死代码）:", sorted(set(mx) - registered))

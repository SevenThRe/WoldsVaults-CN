"""内置服务器列表（servers.dat）的 NBT 生成。

官方整合包在 ``overrides/servers.dat`` 与 ``overrides/configureddefaults/servers.dat``
里内置了 8 台国外社区服。汉化版面向中文单机/自建服玩家，这些外服无用，故替换为
自建服（或不内置任何服务器）。

servers.dat 的 NBT 结构（顶层 TAG_Compound，根名为空串）：

    {
      "servers": TAG_List<TAG_Compound> [
        { "ip": str, "name": str, "icon": str(base64 PNG, 可选) }
        ...
      ]
    }

字段顺序固定为 ip → name → icon；icon 可省略（游戏内显示默认图标）。
"""

from __future__ import annotations

import struct

#: 汉化版内置的唯一服务器（自建服）。留空列表可让客户端不内置任何服务器。
#: 如需多台，在此追加 dict 即可。
DEFAULT_SERVERS: list[dict] = [
    {"ip": "nbc.rainplay.cn:52481", "name": "nbc.rainplay.cn:52481"},
]


def _nbt_string(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack(">H", len(b)) + b


def write_servers_dat(servers: list[dict] | None = None) -> bytes:
    """生成 ``servers.dat`` 的完整 NBT 字节流。

    ``servers`` 每项是 ``dict(ip=..., name=..., icon=...)``，icon 可省略。
    缺省用 :data:`DEFAULT_SERVERS`。
    """
    if servers is None:
        servers = DEFAULT_SERVERS

    out = bytearray()
    out.append(10)          # 根：TAG_Compound
    out += _nbt_string("")  # 根名：空串

    out.append(9)               # "servers"：TAG_List
    out += _nbt_string("servers")
    out.append(10)              # 元素类型 TAG_Compound
    out += struct.pack(">i", len(servers))

    for s in servers:
        # 列表元素是匿名 TAG_Compound：直接依次写字段，最后 TAG_End 收尾
        for key in ("ip", "name", "icon"):
            if key not in s or s[key] is None:
                continue
            out.append(8)              # TAG_String
            out += _nbt_string(key)
            out += _nbt_string(str(s[key]))
        out.append(0)                  # 结束该元素 compound

    out.append(0)                      # 结束根 compound
    return bytes(out)

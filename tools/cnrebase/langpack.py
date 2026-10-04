"""自包含的「语言包」模块：资源包生成 + 模组 jar 语言表确定性合并。

为什么需要这条通道
------------------
同一个 ``assets/<ns>/lang/zh_cn.json`` 可能被多个资源包同时提供（我们的汉化
mod jar、第三方模组 jar、I18n 下载包……）。1.18.2 Forge（40.x）的**实际**语义
是**按 key 合并**（字节码已核）：

* ``ResourceManager#getResources``（SRG ``m_7396_``）返回该路径下**所有**相关
  包的资源（一个 ``List<Resource>``），并非「取优先级最高的一份」；
* ``LanguageManager`` / ``ClientLanguage`` 依次对列表里每个文件调
  ``Language.loadFromJson(..., map::put)`` —— 于是**逐 key 合并、后加载者优先**
  （``options.txt`` 的 ``resourcePacks`` 里**越靠后**优先级越高）。

由此两条推论，正是本模块设计的依据：

* 「整文件覆盖」是**误判** —— 只写稀疏增量并不会清空别的包的键；省略某个 key
  也无法「屏蔽」它，要屏蔽只能显式覆盖成别的文案。所以本模块**不做任何空值/
  半份文件清空**逻辑，合并一律走逐 key ``put``。
* 但同一 key 被两个包同时提供时，胜负完全由**包顺序**决定，而顺序里含
  I18n（``i18nupdatemod.core.GameConfig#addResourcePack``）对 ``options.txt``
  的改写 —— 它**只在 id 不存在时**才 `filter(!contains(keyword))` 后 append
  置尾；id 已存在则 `contains` 早退、顺序一字不动。也就是说「置尾」是**有条件、
  可被后续早退稳定下来**的，而非每启动重排。这仍属不受本项目控制的因素 ——
  尤其 I18n 升级/换 zip 名（id 变化）时会重新置尾。详见
  :func:`build_resource_pack` 的命名提醒。

本模块提供一条**确定性**通道来消除这种竞争：

* :func:`patch_jar` 把「模组 jar 自带的那份 ``zh_cn.json``」与「我们的译文」
  先按 key 合并，再写回**该模组自己的 jar**。写回后该 jar 内部就只有一份文件，
  模组原有的键与我们的键共存，竞争被彻底消除 —— 无论资源包顺序如何结果一致。
* :func:`build_resource_pack` 把（通常已合并好的）语言表另行打成标准资源包
  zip，供不注入 jar 时的备用分发。注意：作为普通资源包，它与模组自带文件是
  **并集**关系；能否盖过 I18n 下载包取决于载入顺序，不由本模块保证。

合并策略是全模块的总纲：**以模组自带内容为底、我方译文按 key 叠加其上**。
``patch_jar`` 必须带底 —— 它把模组自己的那份文件**替换**掉，若只写稀疏增量，
``mekanism``、``occultism`` 这类自带几百上千中文键的模组会整片中文消失；
``merge_files`` 的「后层覆盖前层」正对应运行时「后加载的包优先」这条语义。

硬约束
------
1. 零第三方依赖，只用标准库。
2. 不编译、不调用任何 Java / gradle。
3. zip 重写**字节保真**：除目标 ``assets/<ns>/lang/zh_cn.json`` 外，其余条目
   的原始内容与 CRC 必须与源一致（读 ``zf.read(info)`` 后原样写入，复用源的
   ``ZipInfo`` 元数据）。
4. 语言表 JSON 落盘统一 ``ensure_ascii=False, sort_keys=True``（键排序保证可复现）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

if __package__ in (None, ""):  # 允许 python tools/cnrebase/langpack.py 直接执行
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.cnrebase import fsutil  # noqa: E402  (须在 sys.path 处理后导入)

__all__ = [
    "load_lang_zip",
    "load_lang_dir",
    "merge_files",
    "build_resource_pack",
    "find_vendor_jars",
    "conflicts",
    "patch_jar",
    "pack_name_is_safe",
    "main",
    "DEFAULT_PACK_FORMAT",
    "DEFAULT_PACK_NAME",
    "I18N_KEYWORD",
]

#: 语言表的资源路径形态：``assets/<ns>/lang/zh_cn.json``。
#: 命名空间是**单段**路径（不含 ``/``），因此用 ``[^/]+`` 精确匹配，
#: 避免把 ``assets/a/b/lang/zh_cn.json`` 这种非法结构也吞进来。
_LANG_RE = re.compile(r"^assets/([^/]+)/lang/zh_cn\.json$")

#: 新建 zip 条目时使用的固定时间戳。zip 最早可表示的时间是 1980-01-01，
#: 取它作为「无源时间」的确定值，让同样输入的产物逐字节可复现。
_EPOCH_DT = (1980, 1, 1, 0, 0, 0)

#: 合法命名空间文法。MC 的 ResourceLocation 命名空间就是 ``[a-z0-9_.-]``，
#: **不含 ``/``**；``.`` 单独或 ``..`` 作为路径段会造成 zip 路径穿越，
#: 必须显式拒绝。写侧入口（:func:`build_resource_pack` / :func:`patch_jar`）
#: 一律先用 :func:`_check_ns` 过一遍。
_NS_RE = re.compile(r"^[a-z0-9_.-]+$")

#: 资源包格式版本。1.18.2 对应 8（1.16.2–1.18.2 皆为 8）。
DEFAULT_PACK_FORMAT = 8

#: ``pack.mcmeta`` 描述默认值。
DEFAULT_PACK_NAME = "woldsvaults_cn 语言包"

#: I18n 对 ``options.txt`` 的 ``resourcePacks`` 过滤器按**子串**匹配这个关键字。
#: 其 append 分支为 ``filter(!id.contains(keyword))``，会**静默删除**所有含该
#: 子串的条目；因此本地烘焙包的**文件名不能包含它**（见 :func:`pack_name_is_safe`）。
I18N_KEYWORD = "Minecraft-Mod-Language-Modpack"


def pack_name_is_safe(name: str) -> bool:
    """给定的资源包 zip 名是否安全（文件名不含 I18n 的子串过滤器关键字）。

    只检查文件名部分（所在目录可自由命名）。用于集成阶段对烘焙包命名做前置校验，
    避免踩 I18n ``addResourcePack`` 的「静默删除同关键字条目」坑（见模块与
    :func:`build_resource_pack` 的说明）。
    """
    return I18N_KEYWORD not in Path(name).name


# --------------------------------------------------------------------------- #
# 内部工具
# --------------------------------------------------------------------------- #
def _lang_bytes(obj: dict) -> bytes:
    """语言表 / mcmeta 的统一序列化。

    ``ensure_ascii=False`` 让中文以原字符落盘（体积更小、人可读）；
    ``sort_keys=True`` 让同一逻辑内容无论插入顺序如何都产出相同字节 ——
    这是「可复现构建」的前提，也方便 diff。
    """
    return json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _parse_lang_bytes(raw: bytes) -> dict[str, str]:
    """把一份语言表字节解析成「只含非空字符串值」的字典。

    为什么只留字符串：语言文件里偶有嵌套结构 / ``null`` / 数字，直接透传会让
    后续 JSON 出现非字符串叶子，玩家侧加载时**整份文件静默丢弃**。空串同理 ——
    MC 对空串按「缺失」渲染键名，保留它们只会污染合并结果。任一环节出错
    （损坏字节、非 dict）都退化为空字典，让调用方按「该文件不存在」处理。
    """
    try:
        obj = json.loads(raw.decode("utf-8", "replace").lstrip("\ufeff"))
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    return {k: v for k, v in obj.items() if isinstance(v, str) and v.strip()}


def _copy_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    """复制 ``ZipInfo`` 元数据，尽量保住原始字节行为。

    与 ``packs._copy_info`` 同源：时间戳、压缩方式、权限位、UTF-8 文件名标志
    都要带过去，否则重打包后的 jar 与源在结构上不再等价。CRC 不在这里设置 ——
    ``writestr`` 会依据写入的**原始内容**重新计算，内容一致则 CRC 必然一致。
    """
    ni = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    ni.compress_type = info.compress_type
    ni.external_attr = info.external_attr
    ni.internal_attr = info.internal_attr
    ni.create_system = info.create_system
    ni.comment = info.comment
    if info.flag_bits & 0x800:  # UTF-8 文件名标志
        ni.flag_bits |= 0x800
    return ni


def _fixed_info(name: str, compress_type: int = zipfile.ZIP_DEFLATED) -> zipfile.ZipInfo:
    """构造一个**时间戳固定**的 ``ZipInfo``，供可复现构建使用。

    ``writestr`` 若只给裸名字会取「当前时间」，两次调用字节不同（QA 实测过）。
    想固定某语言文件的元数据时统一走这里，时间戳取 :data:`_EPOCH_DT`。
    """
    ni = zipfile.ZipInfo(name, date_time=_EPOCH_DT)
    ni.compress_type = compress_type
    return ni


def _check_ns(ns: str) -> None:
    """校验命名空间是否合法，非法则抛 ``ValueError``。

    为什么必须拦：命名空间会被拼进 zip 条目路径
    ``assets/<ns>/lang/zh_cn.json``。若允许 ``..`` / ``../../evil``，解包后
    会**逃出包根**（路径穿越，QA 已复现）。MC 的命名空间文法就是
    ``^[a-z0-9_.-]+$`` —— **不含 ``/``**，因此一律拒绝，并把违规值写进异常
    消息便于定位；此外 ``.`` / ``..`` 虽能通过字符类，却是路径段意义上的
    穿越元字符，**显式单独拒绝**。用 ``fullmatch`` 而非 ``match`` —— Python 的
    ``$`` 允许串尾换行，``match`` 会放过 ``"demo\n"`` 这种带换行的非法名。
    """
    if (
        not isinstance(ns, str)
        or _NS_RE.fullmatch(ns) is None
        or ns in (".", "..")
    ):
        raise ValueError(
            f"非法命名空间 {ns!r}：须匹配 ^[a-z0-9_.-]+$（不含 '/'，且不得为 '.'、'..'、空串）"
        )


def _read_json_file(path: str | Path) -> dict:
    """读取磁盘上的 JSON 文件（用于 CLI 的 ``--ns-lang`` / ``patch_json``）。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# 读取
# --------------------------------------------------------------------------- #
def load_lang_zip(
    path: str | Path,
    only_namespaces: set[str] | None = None,
) -> dict[str, dict[str, str]]:
    """从一个 zip（模组 jar 或资源包）里读出所有 ``zh_cn`` 语言表。

    只认 ``assets/<ns>/lang/zh_cn.json`` 这一固定形态。同一命名空间若出现
    多份（畸形包），按 zip 内顺序后者覆盖前者 —— 与「整文件覆盖」的直觉一致。
    ``only_namespaces`` 用于把扫描范围收窄到关心的命名空间（例如只处理我方
    有译文的），避免为大包做无用解析。

    返回 ``{namespace: {key: value}}``，**只保留值为 str 且 strip 后非空的条目**。
    """
    out: dict[str, dict[str, str]] = {}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            m = _LANG_RE.match(name)
            if m is None:
                continue
            ns = m.group(1)
            if only_namespaces is not None and ns not in only_namespaces:
                continue
            pairs = _parse_lang_bytes(zf.read(name))
            out.setdefault(ns, {}).update(pairs)
    return out


def load_lang_dir(
    root: str | Path,
    only_namespaces: set[str] | None = None,
) -> dict[str, dict[str, str]]:
    """递归扫描目录树，找出所有 ``assets/<ns>/lang/zh_cn.json``。

    用在「已解压的资源包目录 / 数据目录」场景。按 ``<ns>`` 聚合，语义与
    :func:`load_lang_zip` 完全一致（含过滤规则），便于两路输入直接互相合并。
    """
    root = Path(root)
    out: dict[str, dict[str, str]] = {}
    if not root.is_dir():
        return out
    # 先按路径名收敛（rglob 命中文件名即可），再校验父级结构，
    # 避免为了匹配少量文件而遍历整棵树并逐条正则。
    for p in sorted(root.rglob("zh_cn.json")):
        if p.parent.name != "lang":
            continue
        ns_dir = p.parent.parent
        if ns_dir.parent.name != "assets":
            continue
        ns = ns_dir.name
        if only_namespaces is not None and ns not in only_namespaces:
            continue
        pairs = _parse_lang_bytes(p.read_bytes())
        out.setdefault(ns, {}).update(pairs)
    return out


# --------------------------------------------------------------------------- #
# 合并
# --------------------------------------------------------------------------- #
def merge_files(
    *layers: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    """多层语言表按命名空间分组、**逐 key** 合并。

    ``layers`` 从底到顶排列：**后面的层覆盖前面的层**（同名键取后到者）。
    这正是 MC 运行时的真实语义 —— ``getResources`` 返回该路径下所有包的资源
    列表，``LanguageManager`` 依次 ``put`` 进同一张 map（后加载者优先）。
    我们用它在离线阶段把「模组自带 zh（底）> 我方译料（顶）」等多层预先折叠成
    最终一份，从而不必依赖运行期的资源包顺序。

    设计要点：合并是**按 key 逐条**的，不是整份替换，也**不做任何空值清空**。
    因此底层独有的键会被保留，顶层的键会生效 —— 这既守住了「模组原有中文不能
    丢」，又让我们的译文能覆盖「伪翻译」等同名键。注意原版语义下「省略某个 key」
    并不能屏蔽它，故本函数不提供、也不该提供那种语义。
    """
    out: dict[str, dict[str, str]] = {}
    for layer in layers:
        if not layer:
            continue
        for ns, table in layer.items():
            if not isinstance(table, dict):
                continue
            out.setdefault(ns, {}).update(table)
    return out


# --------------------------------------------------------------------------- #
# 资源包
# --------------------------------------------------------------------------- #
def build_resource_pack(
    dest: str | Path,
    ns_lang: dict[str, dict[str, str]],
    pack_name: str,
    pack_format: int = DEFAULT_PACK_FORMAT,
    extra_files: dict[str, bytes] | None = None,
) -> Path:
    """把 ``ns_lang`` 打成标准资源包 zip，返回产物路径。

    结构：

    * ``pack.mcmeta`` —— ``{"pack": {"pack_format": 8, "description": pack_name}}``。
      ``description`` 用纯字符串（而非 JSON 文本组件），兼容性最好。
    * ``assets/<ns>/lang/zh_cn.json`` —— 每个命名空间一份，键已排序。
    * ``extra_files`` —— ``{zip 内路径: bytes}``，用于塞 ``pack.png`` /
      ``README.txt`` / ``LICENSE`` 等附加件；直接按给定路径原样写入。

    资源包与「注入模组 jar」是两条分发通道：前者让玩家手动启用，注入后其内容
    与模组自带文件在运行时按 key **并集**（后续包可覆盖同 key）；后者把结果
    固化进模组 jar、内部只剩一份文件，因而**确定性**、不受包顺序影响。若这张
    资源包需要盖过 I18n 下载包，还要保证它在载入顺序里更靠后 —— 那不由本函数
    负责，只在此说明 I18n 的真实行为（字节码已核）：其 ``addResourcePack``
    **仅在 id 不存在时**才 append 置尾，id 已存在则早退、顺序保持原样；因此
    玩家手工把本包排到 I18n 包之后，在 I18n 的 covertFileName 不变时可稳定生效，
    I18n 升级/换 zip 名（id 变化）后会重新置尾、可能反超。

    ⚠️ **命名提醒**：I18n 的 append 分支用的是**子串**过滤
    ``filter(!id.contains(keyword))``（keyword = :data:`I18N_KEYWORD`），一旦被
    触发会**静默删掉 options.txt 里所有含该子串的条目** —— 包括你自己烘焙的包。
    故本产物的文件名务必避开该子串（用 :func:`pack_name_is_safe` 校验），
    例如 ``CFPA-CN-Baked-1.18.2.zip``。

    所有命名空间先经 :func:`_check_ns` 校验（拒绝 ``/`` / ``.`` / ``..`` / 空串），
    因为 ns 会被拼进 zip 条目路径，非法值会导致路径穿越。所有条目用固定时间戳
    :data:`_EPOCH_DT` 写入，保证同输入逐字节可复现。
    """
    # 先整体校验命名空间，避免在磁盘上留下半截产物后再抛异常。
    namespaces = sorted(ns_lang)
    for ns in namespaces:
        _check_ns(ns)

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    mcmeta = {"pack": {"pack_format": int(pack_format), "description": pack_name}}
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        zf.writestr(_fixed_info("pack.mcmeta"), _lang_bytes(mcmeta))
        for ns in namespaces:
            zf.writestr(
                _fixed_info(f"assets/{ns}/lang/zh_cn.json"), _lang_bytes(ns_lang[ns])
            )
        if extra_files:
            for name, data in extra_files.items():
                zf.writestr(_fixed_info(name), data)
    return dest


# --------------------------------------------------------------------------- #
# 冲突探测
# --------------------------------------------------------------------------- #
def find_vendor_jars(mods_dir: str | Path) -> dict[Path, set[str]]:
    """扫描 ``mods_dir`` 下所有 ``*.jar``。

    返回 ``{jar 路径: 该 jar 自带的 zh_cn 命名空间集合}``。**所有** jar 都会
    出现（没有 ``zh_cn`` 的映射到空集合），这样调用方一眼能看出「盘上有哪些
    模组」「哪些模组自带中文」。损坏 / 非 zip 的 jar 视为空集合，不抛异常 ——
    实际整合包里偶尔会混入占位文件，扫描不应因此中断。
    """
    out: dict[Path, set[str]] = {}
    d = Path(mods_dir)
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.jar")):
        nss: set[str] = set()
        try:
            with zipfile.ZipFile(p) as zf:
                for name in zf.namelist():
                    m = _LANG_RE.match(name)
                    if m is not None:
                        nss.add(m.group(1))
        except Exception:
            nss = set()
        out[p] = nss
    return out


def conflicts(
    vendor_jars: dict[Path, set[str]],
    ours: dict[str, dict[str, str]],
) -> dict[Path, set[str]]:
    """求「同路径竞争」：模组自带 zh_cn 的命名空间 ∩ 我方有译文的命名空间。

    只需要处理**交集**：模组没有 zh_cn 的命名空间不存在竞争（我方文件独占，
    必生效）；我方没有译文的命名空间也无从合并。返回的每个 jar 都对应一组
    需要走 :func:`patch_jar` 的命名空间，只有非空的 jar 才列出。
    """
    our_ns = set(ours)
    out: dict[Path, set[str]] = {}
    for jar, nss in vendor_jars.items():
        hit = nss & our_ns
        if hit:
            out[jar] = set(hit)
    return out


# --------------------------------------------------------------------------- #
# 注入模组 jar
# --------------------------------------------------------------------------- #
def patch_jar(
    src: str | Path,
    dst: str | Path,
    patches: dict[str, dict[str, str]],
) -> int:
    """把语言表**字节保真**地并入模组 jar，返回被写入/新建的语言表文件数。

    语义（关键，别改）：

    * 对 ``patches`` 里的每个 ``namespace``，读该 jar 内已有的
      ``assets/<ns>/lang/zh_cn.json``（**没有则视为 ``{}``**），用
      ``patches[ns]`` 覆盖其上得到合并结果，再写回同名路径。
    * 之所以必须「以自带为底」，是因为本函数把该 jar 内那份文件**整份替换**
      掉 —— 同一个 jar 里只会有一份同名文件，无法靠「多包按 key 合并」来补齐。
      若只写稀疏增量，模组自带的那几百上千条中文会整片消失。逐 key 覆盖则让
      我们的译文能改动「伪翻译」等同名键，同时保住其余中文。
    * 其余**所有**条目（含其他语言文件、class、清单……）原样搬运：解压后按
      源 ``ZipInfo`` 的 ``date_time`` / ``compress_type`` 等元数据重新写入，
      内容不变则 CRC 不变。

    未出现在 ``patches`` 里的命名空间不动；``patches`` 里已有 zh_cn 的命名
    空间被**替换**（条目数不变），缺失的被**新建**（条目数 +1）。返回的计数
    即这两类之和，通常等于 ``len(patches)``。

    ``patches`` 的每个命名空间先经 :func:`_check_ns` 校验：ns 会被拼进 zip
    条目路径，``..`` / 含 ``/`` 之类非法值会造成解包时的路径穿越，一律拒绝。

    **有意不保证「整包逐字节可复现」**（勿当缺陷）：本函数只是**备用通道**，
    当前流水线走资源包；其正确性标准是「非目标条目 CRC 不变 + ``testzip()``
    完好 + 目标语言表键不丢」，**不含**整包 sha256 稳定。可复现性契约只压在
    构建产物（汉化模组 jar / 客户端包 / 服务端包 / 汉化资源包）上。原因是
    非目标条目走的是「解压后按源元数据重新写入」，deflate 压缩流可能因压缩器
    版本/级别不同与源不逐字节一致（CRC 与未压缩内容仍必然一致）。若将来确需
    整包稳定，再改为直接搬运原始压缩流。
    """
    src, dst = Path(src), Path(dst)

    # 先校验命名空间，非法值在动源/写产物之前就抛出。
    for ns in patches:
        _check_ns(ns)

    dst.parent.mkdir(parents=True, exist_ok=True)

    # 目标路径 -> 命名空间。用路径做查表键，避免在循环里反复拼字符串。
    targets = {f"assets/{ns}/lang/zh_cn.json": ns for ns in patches}
    written = 0

    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(
        dst, "w", zipfile.ZIP_DEFLATED, allowZip64=True
    ) as zout:
        handled: set[str] = set()
        for info in zin.infolist():
            name = info.filename
            if name in targets:
                ns = targets[name]
                merged = _parse_lang_bytes(zin.read(info))
                merged.update(patches[ns])
                zout.writestr(_copy_info(info), _lang_bytes(merged))
                handled.add(name)
                written += 1
            else:
                # 非目标条目：原样搬运，复用源元数据。
                zout.writestr(_copy_info(info), zin.read(info))

        # 该 jar 原本没有的目标语言文件 —— 新建条目。
        for name, ns in targets.items():
            if name in handled:
                continue
            ni = zipfile.ZipInfo(name, date_time=_EPOCH_DT)
            ni.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(ni, _lang_bytes(dict(patches[ns])))
            written += 1

    return written


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _cmd_build_pack(args: argparse.Namespace) -> int:
    ns_lang = _read_json_file(args.ns_lang)
    if not isinstance(ns_lang, dict):
        print(f"--ns-lang 必须是一个 JSON 对象: {args.ns_lang}", file=sys.stderr)
        return 2
    dest = build_resource_pack(args.out_zip, ns_lang, args.name)
    total = sum(len(v) for v in ns_lang.values())
    print(f"资源包已生成: {dest}")
    print(f"  命名空间 {len(ns_lang)} 个 / 键 {total} 条 / pack_format={DEFAULT_PACK_FORMAT}")
    return 0


def _cmd_patch_jars(args: argparse.Namespace) -> int:
    mods_dir = Path(args.mods_dir)
    out_dir = Path(args.out_dir)
    doc = _read_json_file(args.patch_json)
    jars = doc.get("jars") if isinstance(doc, dict) else None
    if not isinstance(jars, dict):
        print('patch_json 必须是 {"jars": {"<jar名>": {ns: {k: v}}}}', file=sys.stderr)
        return 2

    done = 0
    total_files = 0
    missing: list[str] = []
    for jar_name in sorted(jars):
        src = mods_dir / jar_name
        if not src.is_file():
            missing.append(jar_name)
            print(f"  跳过（源不存在）: {jar_name}")
            continue
        dst = out_dir / jar_name
        n = patch_jar(src, dst, jars[jar_name])
        done += 1
        total_files += n
        print(f"  {jar_name}: 写入 {n} 份语言表 -> {dst}")
    print(f"处理完成: {done} 个 jar / 共写入 {total_files} 份语言表 -> {out_dir}")
    if missing:
        print(f"  缺失 {len(missing)} 个 jar: {', '.join(missing)}")
    return 0


def _cmd_conflicts(args: argparse.Namespace) -> int:
    ours = _read_json_file(args.ours_json)
    if not isinstance(ours, dict):
        print(f"ours_json 必须是 {ns: {k: v}} 对象: {args.ours_json}", file=sys.stderr)
        return 2
    vendor = find_vendor_jars(args.mods_dir)
    hit = conflicts(vendor, ours)
    payload = {str(p): sorted(nss) for p, nss in hit.items()}
    fsutil.write_text(
        args.out_json,
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )
    print(f"扫描 jar {len(vendor)} 个，其中 {len(hit)} 个与我方译文冲突")
    print(f"冲突已写入: {args.out_json}")
    return 0


def _cmd_selftest(_args: argparse.Namespace) -> int:
    from tools.cnrebase import langpack_selftest

    return langpack_selftest.run()


def main(argv: list[str] | None = None) -> int:
    """命令行入口。子命令见模块 docstring 之外的 README / 集成说明。"""
    parser = argparse.ArgumentParser(
        prog="python -m tools.cnrebase.langpack",
        description="语言包通道：资源包生成 + 模组 jar 语言表确定性合并",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build-pack", help="生成标准资源包 zip")
    p_build.add_argument("out_zip", help="产物 zip 路径")
    p_build.add_argument(
        "--ns-lang", dest="ns_lang", required=True,
        help="JSON 文件，结构 {ns: {key: value}}",
    )
    p_build.add_argument("--name", default=DEFAULT_PACK_NAME, help="资源包显示名")
    p_build.set_defaults(func=_cmd_build_pack)

    p_patch = sub.add_parser("patch-jars", help="把语言表并入模组 jar")
    p_patch.add_argument("mods_dir", help="源 mods 目录")
    p_patch.add_argument("patch_json", help='JSON: {"jars": {"<jar名>": {ns: {k: v}}}}')
    p_patch.add_argument("out_dir", help="输出目录（同名 jar）")
    p_patch.set_defaults(func=_cmd_patch_jars)

    p_conf = sub.add_parser("conflicts", help="导出同路径竞争清单")
    p_conf.add_argument("mods_dir", help="源 mods 目录")
    p_conf.add_argument("ours_json", help="我方译文 JSON: {ns: {k: v}}")
    p_conf.add_argument("out_json", help="冲突结果输出 JSON 路径")
    p_conf.set_defaults(func=_cmd_conflicts)

    p_self = sub.add_parser("selftest", help="运行自检")
    p_self.set_defaults(func=_cmd_selftest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

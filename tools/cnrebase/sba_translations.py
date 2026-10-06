"""SkyBlockAddon 8.2 CN jar 的翻译表（纯文本映射，键为原文精确串）。

术语约定（沿用 woldsvaults 译料层）：
  transmog=幻化、Jewel=宝石、Vault=宝库、Soulbound=灵魂绑定。
模组名惯例：Create=机械动力、Mekanism=通用机械、AE2=应用能源、
  Refined Storage=精炼存储、Thermal=热力系列。

不能翻译的键（数据/匹配用，仅在此备注）：
  * registries/permissions/*.json 的 ``category`` 字段 —— PermissionManager
    用 equalsIgnoreCase 与 GUI 的 category_id 匹配，翻译会让菜单变空；
  * ``id`` / ``triggers`` / ``conditions`` / ``item`` —— 数据字段；
  * ``%...%`` 占位符 —— 运行时替换。
"""

# --------------------------------------------------------------------------- #
# 权限项显示名（display_name 组件里的 text）
# --------------------------------------------------------------------------- #
PERM_NAME = {
    "Activate Waystones": "激活路标石碑",
    "Animal Pen": "动物围栏",
    "Artifact's": "神器",
    "Ascension": "飞升",
    "Attack Entities": "攻击实体",
    "Backpacks — Open": "背包 — 打开",
    "Block Carpentry": "方块木工",
    "Buttons & Levers": "按钮与拉杆",
    "Chestmonster": "箱子怪",
    "Collect XP Orbs": "收集经验球",
    "Colossal Chests": "巨型箱子",
    "Companions": "伙伴",
    "Cooking for Blockheads": "烹饪方块",
    "Crates": "板条箱",
    "Create More Burners": "机械动力：更多燃烧器",
    "Create — Assemble Trains": "机械动力 — 组装列车",
    "Create — Copycats": "机械动力 — 复制方块",
    "Create — Machines": "机械动力 — 机器",
    "Create — Seats": "机械动力 — 座位",
    "Create — Train Controls": "机械动力 — 列车操控",
    "Create: Addition — Electrical": "机械动力：附加包 — 电气",
    "Create: Railways": "机械动力：铁路",
    "Crucible": "坩埚",
    "Crystal Modification": "水晶改造",
    "Decks & Cards": "牌组与卡牌",
    "Destroy Blocks": "破坏方块",
    "Easy Piglins": "简单猪灵",
    "Easy Villagers": "简单村民",
    "Elevators": "电梯",
    "Enter Vault": "进入宝库",
    "Flux Networks": "Flux 网络",
    "Furniture — Cooler": "家具 — 冷藏箱",
    "Furniture — Fridge": "家具 — 冰箱",
    "Furniture — Kitchen Sink": "家具 — 厨房水槽",
    "Furniture — Mailbox": "家具 — 邮箱",
    "Furniture — Storage": "家具 — 存储",
    "Gear": "装备",
    "Hostile Mobs": "敌对生物",
    "Interact with AE2 Network": "与应用能源网络互动",
    "Interact with Barrels": "与木桶互动",
    "Interact with Blocks": "与方块互动",
    "Interact with Chests": "与箱子互动",
    "Interact with Containers": "与容器互动",
    "Interact with Create Links": "与机械动力链接器互动",
    "Interact with Doors & Trapdoors": "与门和活板门互动",
    "Interact with Fence Gates": "与栅栏门互动",
    "Interact with Furnaces": "与熔炉互动",
    "Interact with Hoppers": "与漏斗互动",
    "Interact with Item Frames": "与物品展示框互动",
    "Interact with Refined Storage Network": "与精炼存储网络互动",
    "Interact with Shulker Boxes": "与潜影盒互动",
    "Interact with Simple Storage Network": "与简易存储网络互动",
    "Island Admin": "岛屿管理",
    "Jewels": "宝石",
    "Mekanism — Machines": "通用机械 — 机器",
    "Mekanism — QIO Storage": "通用机械 — QIO 存储",
    "Passive Mobs": "被动生物",
    "Personal": "个人",
    "Pickup/Drop Items": "拾取/丢弃物品",
    "Place Blocks": "放置方块",
    "Place/Pickup Fluids": "放置/拾取流体",
    "Recycle": "回收",
    "Redstone Delays": "红石延迟元件",
    "Sleep in Beds": "睡觉",
    "Spawn Entities": "生成实体",
    "Storage Drawers": "存储抽屉",
    "Teleportation": "传送",
    "Thermal Machines": "热力系列机器",
    "Tools": "工具",
    "Trample Crops": "踩踏农田",
    "Use Anvils": "使用铁砧",
    "Use Bone Meal": "使用骨粉",
    "Use Nether Portal": "使用下界传送门",
    "Use Vehicles": "使用载具",
    "Wardrobe": "装备柜",
}

# --------------------------------------------------------------------------- #
# lore 与 join.entries 的纯文本（精确匹配替换）
# --------------------------------------------------------------------------- #
PERM_LORE = {
    # --- 固定句式 ---
    "» Click to toggle the status of this permission for %data_group_name%.":
        "» 点击切换「%data_group_name%」分组是否拥有此权限。",
    "♦ Status: ": "♦ 状态：",
    "♦ Allows: ": "♦ 允许：",
    "♦ Contains: ": "♦ 包含：",
    # --- Allows/Contains 说明文本 ---
    "AE2": "应用能源 (AE2)",
    "AE2 Things": "应用能源：附属 (AE2 Things)",
    "Accumulator": "蓄能器",
    "Alchemy Table": "炼金台",
    "All Vault Crates": "全部宝库板条箱",
    "Alternator": "交流发电机",
    "Animal Jar": "动物罐",
    "Architect's Workbench": "建筑师工作台",
    "Artifact Tome": "神器典籍",
    "Ascension Forge": "飞升锻造台",
    "Assembling, disassembling, and renaming Trains at a Train Station. "
    "Separate from create_train_controls, so someone can drive a train "
    "without being able to (dis)assemble it.":
        "在列车站组装、拆卸和重命名列车。与 create_train_controls 分开，"
        "因此可以只允许开车而不允许（拆）组装。",
    "Augment Station": "强化台",
    "Battery Box": "电池箱",
    "Black Market": "黑市",
    "Blast Furnace": "高炉",
    "Boats": "船",
    "Bone Meal": "骨粉",
    "Bounty Table": "悬赏桌",
    "Cabinets": "橱柜",
    "Card Binder": "卡册",
    "Card Upgrade Station": "卡牌升级台",
    "Catalyst Infusion Table": "催化灌注台",
    "Changing the appearance of Copycat blocks.": "更改复制方块的外观。",
    "Changing the block variant of frame blocks.": "更改框架方块的方块变体。",
    "Chestmonster Hand": "箱子怪之手",
    "Chorus Fruit": "紫颂果",
    "Companion Home": "伙伴之家",
    "Companion Incubator": "伙伴孵化器",
    "Comparator": "比较器",
    "Contraption Controls": "装置操控",
    "Create Repeater/Extender variants": "机械动力中继器/扩展器变体",
    "Crusher": "破碎机",
    "Crystal Workbench": "水晶工作台",
    "Customisation Station": "定制台",
    "Deck Station": "牌组台",
    "Deployer": "部署器",
    "Dispenser": "发射器",
    "Drawers": "抽屉",
    "Dropper": "投掷器",
    "Dynamos": "发电机组",
    "Electric Motor": "电动机",
    "Ender Pearls": "末影珍珠",
    "Energy Cells": "能量电池",
    "Enrichment Chamber": "富集仓",
    "Entering the Vault dimension via a Vault Portal.": "通过宝库传送门进入宝库维度。",
    "Etching Application Table": "蚀刻应用台",
    "Factories": "工厂",
    "Fallback permission for all block interactions.": "所有方块互动的后备权限。",
    "Fan": "风扇",
    "Fence Gates": "栅栏门",
    "Filling and emptying buckets at the kitchen sink.": "在厨房水槽处装桶或清空桶。",
    "Flux Controller": "Flux 控制器",
    "Flux Plug": "Flux 插头",
    "Flux Point": "Flux 点",
    "Flux Storage": "Flux 存储能库",
    "Framed Compact Drawers": "有框紧凑抽屉",
    "Funnels": "漏斗",
    "Furnace": "熔炉",
    "Gear Sealer": "装备封印台",
    "Greed Cauldron": "贪婪坩埚",
    "Identification Stand": "鉴定台",
    "Imbuement Altar": "灌注祭坛",
    "Inscription Table": "铭刻台",
    "Iron Furnaces": "铁熔炉",
    "Jewel Applicator": "宝石镶嵌台",
    "Jewel Crafting Table": "宝石工作台",
    "ME Requester": "ME 请求器 (ME Requester)",
    "Machines": "机器",
    "Mail Box": "信箱",
    "Mechanical Arm": "机械臂",
    "Metallurgic Infuser": "冶金注入机",
    "Millstone": "石磨",
    "Minecarts": "矿车",
    "Mixer": "搅拌器",
    "Place/View/Pickup backpacks": "放置/查看/拾取背包",
    "Post Box variants": "邮箱变体",
    "Press": "压印机",
    "QIO Dashboard": "QIO 面板",
    "QIO Drive Array": "QIO 驱动器阵列",
    "QIO Importer/Exporter": "QIO 输入/输出器",
    "RS Addons": "精炼存储：附加 (RS Addons)",
    "Railing Gates": "栏杆门",
    "Reclamation Altar": "回收祭坛",
    "Refined Storage": "精炼存储",
    "Regular Barrels": "普通木桶",
    "Regular Chests": "普通箱子",
    "Relic Crafting Table": "遗物工作台",
    "Repeater": "中继器",
    "Saddled Entities": "已装鞍的生物",
    "Saw": "机械锯",
    "Schedule Blocks": "调度表方块",
    "Signal Blocks": "信号方块",
    "Sitting on Create Seats (including seats built into trains/contraptions).":
        "坐上机械动力的座位（包括列车/装置上内置的座位）。",
    "Skill Altar": "技能祭坛",
    "Smoker": "烟熏炉",
    "Spirit Extractor": "灵魂提取器",
    "Tool Station": "工具站",
    "Track Observer": "轨道观测器",
    "Train Controls": "列车操控",
    "Train Stations": "列车站",
    "Transmogrification Table": "幻化台",
    "Trapped Chests": "陷阱箱",
    "Trinket Forge": "饰品锻造台",
    "Tunnels": "隧道",
    "Unboxing Station": "开箱台",
    "Unique Safe": "专属保险箱",
    "Valve Handles": "阀门把手",
    "Vault Artisan Station": "宝库工匠台",
    "Vault Barrels (I.E. Living, Ornate)": "宝库木桶（如：生机、华丽）",
    "Vault Chests (I.E. Living, Ornate)": "宝库箱子（如：生机、华丽）",
    "Vault Forge": "宝库锻造台",
    "Vault Recycler": "宝库回收机",
    "Vault Soul Diffuser": "宝库灵魂扩散器",
    "Vault Soul Harvester": "宝库灵魂收割器",
    "Void Crucible": "虚空坩埚",
}

# --------------------------------------------------------------------------- #
# GUI 菜单里的英文（permissions.json 的说明行）
# --------------------------------------------------------------------------- #
GUI_LORE = {
    "» Access special administrative controls.": "» 访问特殊管理控制。",
    "» Change general permissions.": "» 更改基础权限。",
    "» Change redstone permissions.": "» 更改红石权限。",
    "» Change storage permissions.": "» 更改存储权限。",
    "» Change Create mod permissions.": "» 更改机械动力权限。",
    "» Change miscellaneous permissions.": "» 更改杂项权限。",
    "» Change Vault Hunters permissions.": "» 更改宝库猎人权限。",
}

#: set_permission 菜单标题：%group_category% 是代码从 category_id 现算的
#: （GuiEvents 里 capitalize，不经语言文件），要中文只能改模板或补丁字节码。
#: 模板是自己的 GUI 文件（每次启动覆盖到 config），改标题零风险。
SET_PERMISSION_TITLE_OLD = '{"text": "%group_name% - %group_category%"}'
SET_PERMISSION_TITLE_NEW = '{"text": "%group_name% - 权限设置"}'

#: 翻译后允许残留的英文（占位符 / 保留的模组名）
ALLOWED_KEEP = {
    " ", "%data_status% ", ", ", "Animatrix", "RS Requestify",
}


def text_map() -> dict:
    """合并全部纯文本映射（lore + GUI + 权限名）。

    权限名也要进来：同一个英文串既可能是 display_name（组件串），也可能是
    join.entries 里的纯文本枚举项（如 "Animal Pen" 同时出现在两处）。
    """
    out = dict(PERM_LORE)
    out.update(GUI_LORE)
    out.update(PERM_NAME)
    return out

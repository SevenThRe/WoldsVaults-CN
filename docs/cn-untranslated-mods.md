# 未汉化模组清单

> 回答三个问题：**哪些模组没中文**、**每个还差多少**、**先做哪个**。
>
> 本文由 `python -m tools.cnrebase.cli gap-doc` 自动生成，数据取自 `build/cn/todo/vendor-scan.json` 与 `todo-vendor.tsv`，随构建重跑即可保持一致。

## 一、总览

| 指标 | 数量 |
|---|---|
| 第三方命名空间 | 350 |
| 英文键总数 | 71121 |
| 模组自带中文键 | 41692 |
| 缺键（`zh_cn` 里没有） | 35622 |
| 伪翻译（有 `zh_cn` 但值=英文） | 1434 |
| **待译合计**（已滤掉无需翻译的条目） | **36420** |
| **整包零中文**（从未被汉化过） | **188 个命名空间** |
| 有中文但不完整 | 124 |
| 有中文且完整（不必动） | 29 |

零中文的 188 个命名空间贡献了 **30049** 条待译，占全部的 82.5%。

## 二、零中文模组清单（需要汉化，且从未被汉化过）

按待译条数降序。`待译` 已排除「原文为空」与「去掉 printf 占位符后无实义字母」的条目（后者中文本来就该与英文逐字相同）。

| # | 命名空间 | 模组 jar | 英文键 | 待译 |
|---|---|---|---|---|
| 1 | `chipped` | chipped-forge-1.18.2-2.0.1.jar | 7468 | 7467 |
| 2 | `buildscape` | buildscape-3.0.9-VH.jar | 4069 | 4068 |
| 3 | `pneumaticcraft` | pneumaticcraft-repressurized-1.18.2-3.6.4-45.jar | 1987 | 1985 |
| 4 | `buildersdelight` | BuildersDelight-1.18.2-v.1.0.jar | 1494 | 1491 |
| 5 | `luphieclutteredmod` | cluttered-2.1-1.18.2.jar | 1167 | 1166 |
| 6 | `rechiseled` | rechiseled-1.1.5b-forge-mc1.18.jar | 1113 | 1113 |
| 7 | `hexcasting` | hexcasting-forge-1.18.2-0.9.6.jar | 925 | 921 |
| 8 | `openpartiesandclaims` | open-parties-and-claims-forge-1.18.2-0.30.3.jar | 923 | 916 |
| 9 | `davebuildingmod` | dbExtended-1.18.2-6.0.1.jar | 703 | 665 |
| 10 | `createdeco` | createdeco-1.3.3-1.18.2.jar | 625 | 622 |
| 11 | `dyenamicsandfriends` | dyenamicsandfriends-1.18.2-0.1.5.4.jar | 569 | 569 |
| 12 | `mcwfurnitures` | mcw-furniture-3.2.2-mc1.18.2forge.jar | 491 | 490 |
| 13 | `neoncraft2` | neoncraft2-2.2.jar | 324 | 323 |
| 14 | `mcwwindows` | mcw-windows-2.2.1-mc1.18.2forge.jar | 290 | 288 |
| 15 | `auxiliaryblocks` | auxiliaryblocks-1.18.2-0.4.6.jar | 287 | 285 |
| 16 | `xaeroworldmap` | XaerosWorldMap_1.39.12_Forge_1.18.2.jar | 272 | 272 |
| 17 | `vaultfilters` | vaultfilters-1.33.0.jar | 246 | 246 |
| 18 | `rftoolsutility` | rftoolsutility-1.18-4.0.24.jar | 242 | 241 |
| 19 | `integrateddynamicscompat` | IntegratedDynamics-1.18.2-1.17.4.jar | 207 | 207 |
| 20 | `incorporeal` | Incorporeal-3-forge-1.18.2-5.jar | 188 | 187 |
| 21 | `integratedterminals` | IntegratedTerminals-1.18.2-1.4.10.jar | 173 | 172 |
| 22 | `twigs` | twigs-1.1.4-patch4+1.18.2-forge.jar | 172 | 171 |
| 23 | `rechiseledcreate` | rechiseledcreate-1.0.2-forge-mc1.18.jar | 156 | 156 |
| 24 | `mcwfences` | mcw-fences-1.1.1-mc1.18.2forge.jar | 153 | 0 |
| 25 | `modonomicon` | modonomicon-1.18.2-1.33.1.jar | 153 | 150 |
| 26 | `casinocraft` | CasinoCraft_1.18.2_v19.jar | 140 | 140 |
| 27 | `ironfurnaces` | ironfurnaces-1.18.2-3.3.3.jar | 140 | 139 |
| 28 | `hexal` | hexal-forge-1.18.2-0.1.14.jar | 135 | 135 |
| 29 | `blockcarpentry` | blockcarpentry-1.18-0.5.1.jar | 135 | 134 |
| 30 | `dyenamics` | dyenamics-2.0.0.jar | 127 | 127 |
| 31 | `controlengineering` | ControlEngineering-0.1.1.jar | 125 | 124 |
| 32 | `darkutils` | DarkUtilities-Forge-1.18.2-10.1.7.jar | 125 | 124 |
| 33 | `simplylight` | simplylight-1.18.2-1.4.5-build.43.jar | 125 | 124 |
| 34 | `skyblockbuilder` | SkyblockBuilder-1.18.2-3.3.33.jar | 122 | 122 |
| 35 | `resourcify` | Resourcify (1.18.2-forge)-1.3.0.jar | 118 | 118 |
| 36 | `vaultlootbeams` | VaultLootBeams-1.18.2-1.0.2.jar | 118 | 118 |
| 37 | `storagedrawers` | StorageDrawers-1.18.2-10.2.1.jar | 111 | 109 |
| 38 | `thermal_extra` | ThermalExtra 1.18.2-2.0.3.jar | 112 | 109 |
| 39 | `cloudstorage` | cloudstorage-1.1.0-1.18.2.jar | 109 | 108 |
| 40 | `pehkui` | Pehkui-3.7.11+1.18.2-forge.jar | 105 | 104 |
| 41 | `integratedcrafting` | IntegratedCrafting-1.18.2-1.1.6.jar | 104 | 103 |
| 42 | `mcwlights` | mcw-lights-1.0.6-mc1.18.2forge.jar | 103 | 102 |
| 43 | `factory_blocks` | factory-blocks-mod-1.0.1+1.18.2.jar | 101 | 101 |
| 44 | `wildbackport` | wildbackport-1.2.3.jar | 95 | 95 |
| 45 | `brandonscore` | BrandonsCore-1.18.2-3.1.10.283-universal.jar | 92 | 92 |
| 46 | `mcwbridges` | mcw-bridges-2.1.0-mc1.18.2forge.jar | 93 | 92 |
| 47 | `betterdungeons` | YungsBetterDungeons-1.18.2-Forge-2.1.0.jar | 90 | 90 |
| 48 | `lctech` | lctech-1.18.2-0.2.0.2.jar | 90 | 90 |
| 49 | `davespotioneering` | davespotioneering-1.18.2-1.3.1.jar | 91 | 88 |
| 50 | `ftbteams` | ftb-teams-forge-1802.2.11-build.107.jar | 86 | 86 |
| 51 | `curvy_pipes` | curvy_pipes-1.18.2-1.15.6.jar | 86 | 85 |
| 52 | `neruina` | Neruina-2.1.2-forge+1.18.2.jar | 85 | 85 |
| 53 | `botanicalextramachinery` | botanicalextramachinery-1.18.2-1.0.1.jar | 85 | 84 |
| 54 | `pipez` | pipez-1.18.2-1.1.5.jar | 83 | 82 |
| 55 | `smallships` | smallships-forge-1.18.2-2.0.0-b1.0.jar | 81 | 80 |
| 56 | `betterstrongholds` | YungsBetterStrongholds-1.18.2-Forge-2.1.1.jar | 79 | 79 |
| 57 | `mininggadgets` | mininggadgets-1.11.1.jar | 79 | 78 |
| 58 | `yungscavebiomes` | YungsCaveBiomes-1.18.2-Forge-1.1.1.jar | 75 | 74 |
| 59 | `ae2additions` | AEAdditions-1.18.2-3.2.8.jar | 68 | 67 |
| 60 | `draconicadditions` | Draconic-Additions-1.18.2-2.2.7.10-universal.jar | 70 | 67 |
| 61 | `explorerscompass` | ExplorersCompass-1.18.2-1.3.0-forge.jar | 66 | 66 |
| 62 | `reauth` | ReAuth-1.18-Forge-4.0.7.jar | 66 | 65 |
| 63 | `experienceobelisk` | Cognition-v2.0.3-1.18.2.jar | 65 | 64 |
| 64 | `rftoolspower` | rftoolspower-1.18-4.0.9.jar | 65 | 64 |
| 65 | `vaultbeacon` | vaultbeacon-1.0.0.jar | 61 | 61 |
| 66 | `xnet` | xnet-1.18-4.0.9.jar | 58 | 57 |
| 67 | `effortlessbuilding` | effortlessbuilding-1.18-2.40.jar | 69 | 56 |
| 68 | `rottencreatures` | rottencreatures-forge-1.18.2-1.0.0.jar | 57 | 56 |
| 69 | `extremesoundmuffler` | extremesoundmuffler-3.30_forge-1.18.2.jar | 55 | 55 |
| 70 | `more_immersive_wires` | more-immersive-wires-1.18.2-1.1.3.jar | 56 | 55 |
| 71 | `moremekanismprocessing` | MoreMekanismProcessing-1.18.2-2.5.jar | 60 | 55 |
| 72 | `cabletiers` | cabletiers-1.18.2-0.56.jar | 55 | 54 |
| 73 | `rftoolsbase` | rftoolsbase-1.18-3.0.12.jar | 55 | 54 |
| 74 | `irongenerators` | IronGenerators-2.0.2-1.18.2.jar | 55 | 52 |
| 75 | `libx` | LibX-1.18.2-3.2.19.jar | 51 | 51 |
| 76 | `megacells` | MEGACells-1.4.2-1.18.2.jar | 52 | 51 |
| 77 | `xray` | [高级透视] advanced-xray-forge-1.18.2-2.11.0-build.7.jar | 51 | 51 |
| 78 | `secondchanceforge` | secondchanceforge-1.18.2-1.5.0.jar | 49 | 49 |
| 79 | `titanium` | titanium-1.18.2-3.5.11-45.jar | 48 | 47 |
| 80 | `peripherals` | MorePeripherals_1.18.2-1.8.jar | 46 | 45 |
| 81 | `extrastorage` | ExtraStorage-1.18.2-2.2.1.jar | 45 | 44 |
| 82 | `weather_control` | Weather_Control-Forge-1.18.2-2.jar | 42 | 0 |
| 83 | `drippyloadingscreen` | drippyloadingscreen_forge_3.0.12_MC_1.18.2.jar | 41 | 41 |
| 84 | `rftoolsstorage` | rftoolsstorage-1.18-3.0.12.jar | 41 | 40 |
| 85 | `sophisticatedvaultupgrades` | sophisticatedvaultupgrades-1.21.1.jar | 40 | 40 |
| 86 | `tinygates` | tinygates-2.1.1.jar | 40 | 39 |
| 87 | `mantle` | Mantle-1.18.2-1.9.45.jar | 38 | 38 |
| 88 | `sebastrnlib` | sebastrnlib-1.0.2.jar | 37 | 37 |
| 89 | `skyguis` | SkyGUIs-1.18.2-1.2.3.jar | 38 | 37 |
| 90 | `littlecontraptions` | littlecontraptions-forge-1.18.2.2.jar | 36 | 36 |
| 91 | `moreoverlays` | moreoverlays-1.20.12-mc1.18.2.jar | 36 | 36 |
| 92 | `ironchests` | ironchests-2.0.5-forge.jar | 31 | 31 |
| 93 | `valhelsia_core` | valhelsia_core-forge-1.18.2-0.4.0.jar | 31 | 31 |
| 94 | `otyacraftengine` | otyacraftengine-forge-1.18.2-2.14.jar | 29 | 29 |
| 95 | `jadeaddons` | JadeAddons-1.18.2-forge-2.5.0.jar | 28 | 28 |
| 96 | `sfm` | SuperFactoryManager-1.18.2-4.1.1.jar | 29 | 28 |
| 97 | `ktnilcks` | ItemLocks-Forge-1.18.2-1.3.8.jar | 27 | 27 |
| 98 | `dungeons_libraries` | dungeons_libraries-1.18.2-2.0.5-beta.jar | 26 | 26 |
| 99 | `sophisticatedvault` | sophisticatedvault-2.3.0.jar | 23 | 23 |
| 100 | `flashnpcs` | flashnpcs-1.18.2-1.2.0.jar | 23 | 22 |
| 101 | `appbot` | Applied-Botanics-1.0.3.jar | 22 | 21 |
| 102 | `jeiintegration` | jeiintegration_1.18.2-9.0.0.37.jar | 21 | 21 |
| 103 | `observable` | observable-2.2.3-forge.jar | 21 | 21 |
| 104 | `cable_facades` | cable_facades-1.18.2-Forge-2.1.3.jar | 20 | 18 |
| 105 | `citadel` | citadel-1.11.3-1.18.2.jar | 18 | 18 |
| 106 | `citresewn` | CIT Reforged 1.18.jar | 18 | 18 |
| 107 | `dimensionalworldborder` | dimensionalworldborder-1.18.2-2.0.0.1.jar | 18 | 18 |
| 108 | `paucal` | paucal-forge-1.18.2-0.4.7.jar | 17 | 17 |
| 109 | `ae2things` | AE2-Things-1.0.5.jar | 17 | 16 |
| 110 | `cagerium` | cagerium-1.18.2-1.1.6.jar | 16 | 16 |
| 111 | `chunkymcchunkface` | ChunkyMcChunkFace-1.18.2-0.3.4.jar | 16 | 16 |
| 112 | `appmek` | Applied-Mekanistics-1.2.2.jar | 16 | 15 |
| 113 | `cucumber` | Cucumber-1.18.2-5.1.5.jar | 15 | 15 |
| 114 | `mobprocessor` | mobprocessor-1.1.jar | 15 | 15 |
| 115 | `refinedcooking` | refinedcooking-2.0.4.jar | 15 | 14 |
| 116 | `cccbridge` | cccbridge-mc1.18.2-forge-v1.5.1.jar | 11 | 11 |
| 117 | `darkmodeeverywhere` | DarkModeEverywhere-1.18.2-1.1.3.jar | 11 | 11 |
| 118 | `forgivingvoid` | forgivingvoid-forge-1.18.1-6.0.1.jar | 11 | 11 |
| 119 | `minecraft` | the_vault-1.18.2-3.21.5.6573.jar | 11 | 11 |
| 120 | `betterdeserttemples` | YungsBetterDesertTemples-1.18.2-Forge-1.3.1.jar | 10 | 10 |
| 121 | `commoncapabilities` | CommonCapabilities-1.18.2-2.9.1.jar | 10 | 10 |
| 122 | `framedcompactdrawers` | framedcompactdrawers-1.18-4.1.0.jar | 11 | 10 |
| 123 | `vaultfruitbag` | vaultfruitbag-1.0.0.jar | 10 | 10 |
| 124 | `codechickenlib` | CodeChickenLib-1.18.2-4.1.4.488-universal.jar | 9 | 9 |
| 125 | `polylib` | polylib-forge-1801.0.3-build.109.jar | 9 | 9 |
| 126 | `vhatcaniroll` | vhatcaniroll-1.15.4.jar | 9 | 9 |
| 127 | `betterfortresses` | YungsBetterNetherFortresses-1.18.2-Forge-1.0.0.jar | 8 | 8 |
| 128 | `betteroceanmonuments` | YungsBetterOceanMonuments-1.18.2-Forge-1.0.3.jar | 8 | 8 |
| 129 | `geckolib3` | geckolib-forge-1.18-3.0.57.jar | 9 | 8 |
| 130 | `ispawner` | ispawner-1.1.9-forge.jar | 8 | 8 |
| 131 | `measurements` | Measurements-forge-1.18.2-1.3.1.jar | 8 | 8 |
| 132 | `memorysettings` | memorysettings-1.18.2-5.2.jar | 8 | 8 |
| 133 | `bobberdetector` | bobberdetector-0.1.9-1.18.2.jar | 7 | 7 |
| 134 | `fastbench` | FastWorkbench-1.18.2-6.0.2.jar | 7 | 7 |
| 135 | `spirittrace` | spirittrace-1.2.0.jar | 7 | 7 |
| 136 | `vaultcuriosenhancements` | vault_curios_enhancements-1.14.0.jar | 7 | 7 |
| 137 | `appliedcooking` | appliedcooking-1.0.3.jar | 7 | 6 |
| 138 | `javd` | JAVD-3.0.0-build.54+mc1.18.2.jar | 6 | 6 |
| 139 | `matc` | matc-1.2.1.jar | 6 | 0 |
| 140 | `placebo` | Placebo-1.18.2-6.6.7.jar | 6 | 6 |
| 141 | `rsrequestify` | rsrequestify-2.2.0.jar | 7 | 6 |
| 142 | `vaultmapper` | vaultmapper-1.10.jar | 6 | 6 |
| 143 | `laserbridges` | laserbridges-1.18.2-forge-5.jar | 5 | 5 |
| 144 | `masuplots` | masuplots-0.8.0.jar | 5 | 5 |
| 145 | `tectonic` | tectonic-forge-1.18-2.3.5a.jar | 5 | 5 |
| 146 | `betterwitchhuts` | YungsBetterWitchHuts-1.18.2-Forge-1.0.1.jar | 4 | 4 |
| 147 | `dummmmmmy` | MmmMmmMmmMmm-1.18.2-1.5.2.jar | 4 | 4 |
| 148 | `jea` | JustEnoughAdvancements-1.18.2-3.2.0.jar | 4 | 4 |
| 149 | `vaultintegrations` | vaultintegrations-1.18.2-1.0.16.jar | 5 | 4 |
| 150 | `ars_creo` | ars_creo-1.18.2-2.2.0.jar | 3 | 3 |
| 151 | `contenttweaker` | ContentTweaker-forge-1.18.2-1.0.0+13.jar | 3 | 3 |
| 152 | `ftbbackups` | ftbbackups2-forge-1.18.2-1.0.23.jar | 3 | 3 |
| 153 | `integratedterminalscompat` | IntegratedTerminals-1.18.2-1.4.10.jar | 3 | 3 |
| 154 | `just_enough_beacons` | JustEnoughBeacons-Forge-1.18.2-1.0.1.jar | 3 | 3 |
| 155 | `libnonymous` | libnonymous-2.1.0.jar | 3 | 3 |
| 156 | `mcjtylib` | mcjtylib-1.18-6.0.20.jar | 3 | 3 |
| 157 | `mifa` | mifa-forge-1.18.2-1.1.1.jar | 5 | 3 |
| 158 | `selene` | selene-1.18.2-1.17.14.jar | 3 | 3 |
| 159 | `snad` | Snad-1.18.2-1.22.04.15a.jar | 3 | 3 |
| 160 | `vaultarhud` | VaultarHUD-1.3.0-1.18.2.jar | 3 | 3 |
| 161 | `ae2searchimprovements` | ae2searchimprovementsbackport-1.0-all.jar | 2 | 2 |
| 162 | `aeinfinitybooster` | AEInfinityBooster-1.18.2-1.1.0+9.jar | 3 | 2 |
| 163 | `autoreglib` | AutoRegLib-1.7-53.jar | 2 | 2 |
| 164 | `bcc` | BetterCompatibilityChecker-1.1.21-build.48+mc1.18.2.jar | 2 | 2 |
| 165 | `createwalkabletracks` | createwalkabletracks-1.0.0.jar | 2 | 2 |
| 166 | `entityculling` | [实体渲染机制优化] entityculling-forge-1.6.1-mc1.18.2.jar | 2 | 2 |
| 167 | `equipmentcompare` | EquipmentCompare-1.18.2-forge-1.3.3.jar | 2 | 2 |
| 168 | `highlightmapmarkers` | highlightmapmarkers-1.0.2-1.18.2.jar | 2 | 2 |
| 169 | `jeitweaker` | JEITweaker-1.18.2-3.0.0.9.jar | 2 | 2 |
| 170 | `jepp` | jepp-1.18-1.0.0.jar | 2 | 2 |
| 171 | `justzoom` | justzoom_forge_1.0.2-1_MC_1.18.2.jar | 2 | 2 |
| 172 | `terrablender` | TerraBlender-forge-1.18.2-1.2.0.126.jar | 2 | 2 |
| 173 | `tiab` | time-in-a-bottle-2.1.0-mc1.18.1.jar | 3 | 2 |
| 174 | `visual_keybinder` | visual_keybinder-1.18.2 - 0.1.7.jar | 2 | 2 |
| 175 | `bettertridents` | BetterTridents-v3.0.0-1.18.2-Forge.jar | 1 | 1 |
| 176 | `bookmarksharing` | bookmarksharing-jei10-1.4.jar | 1 | 1 |
| 177 | `ccvault` | ccvault-1.1.5-3.15.jar | 1 | 1 |
| 178 | `crafting_on_a_stick` | Crafting-on-a-stick-1.18.2-1.1.1.jar | 1 | 1 |
| 179 | `cristellib` | cristellib-forge-1.0.0.jar | 2 | 1 |
| 180 | `enercell` | enercell-1.18.2-1.0.2.jar | 1 | 1 |
| 181 | `ftbessentials` | ftb-essentials-1802.2.2-build.83.jar | 1 | 1 |
| 182 | `jeimultiblocks` | jeimultiblocks-1.18.2-0.0.2.jar | 1 | 1 |
| 183 | `justenoughprofessions` | JustEnoughProfessions-1.18.2-1.3.0.jar | 1 | 1 |
| 184 | `reeses-sodium-options` | textrues_embeddium_options-0.1.1+mc1.18.2.jar | 1 | 1 |
| 185 | `sophisticatedstorageutils` | sophisticatedstorageutils-1.0.jar | 1 | 1 |
| 186 | `unobtanium` | unobtainium-1.26.3.jar | 1 | 1 |
| 187 | `vending_companions` | companion_locker-3.21.4.jar | 1 | 1 |
| 188 | `voidworld` | voidworld-1.18.2-1.0.0.jar | 1 | 1 |

其中 **42 个模组待译 ≥100 条**，是性价比最高的批次：

| 命名空间 | 模组 jar | 待译 |
|---|---|---|
| `chipped` | chipped-forge-1.18.2-2.0.1.jar | 7467 |
| `buildscape` | buildscape-3.0.9-VH.jar | 4068 |
| `pneumaticcraft` | pneumaticcraft-repressurized-1.18.2-3.6.4-45.jar | 1985 |
| `buildersdelight` | BuildersDelight-1.18.2-v.1.0.jar | 1491 |
| `luphieclutteredmod` | cluttered-2.1-1.18.2.jar | 1166 |
| `rechiseled` | rechiseled-1.1.5b-forge-mc1.18.jar | 1113 |
| `hexcasting` | hexcasting-forge-1.18.2-0.9.6.jar | 921 |
| `openpartiesandclaims` | open-parties-and-claims-forge-1.18.2-0.30.3.jar | 916 |
| `davebuildingmod` | dbExtended-1.18.2-6.0.1.jar | 665 |
| `createdeco` | createdeco-1.3.3-1.18.2.jar | 622 |
| `dyenamicsandfriends` | dyenamicsandfriends-1.18.2-0.1.5.4.jar | 569 |
| `mcwfurnitures` | mcw-furniture-3.2.2-mc1.18.2forge.jar | 490 |
| `neoncraft2` | neoncraft2-2.2.jar | 323 |
| `mcwwindows` | mcw-windows-2.2.1-mc1.18.2forge.jar | 288 |
| `auxiliaryblocks` | auxiliaryblocks-1.18.2-0.4.6.jar | 285 |
| `xaeroworldmap` | XaerosWorldMap_1.39.12_Forge_1.18.2.jar | 272 |
| `vaultfilters` | vaultfilters-1.33.0.jar | 246 |
| `rftoolsutility` | rftoolsutility-1.18-4.0.24.jar | 241 |
| `integrateddynamicscompat` | IntegratedDynamics-1.18.2-1.17.4.jar | 207 |
| `incorporeal` | Incorporeal-3-forge-1.18.2-5.jar | 187 |
| `integratedterminals` | IntegratedTerminals-1.18.2-1.4.10.jar | 172 |
| `twigs` | twigs-1.1.4-patch4+1.18.2-forge.jar | 171 |
| `rechiseledcreate` | rechiseledcreate-1.0.2-forge-mc1.18.jar | 156 |
| `modonomicon` | modonomicon-1.18.2-1.33.1.jar | 150 |
| `casinocraft` | CasinoCraft_1.18.2_v19.jar | 140 |
| `ironfurnaces` | ironfurnaces-1.18.2-3.3.3.jar | 139 |
| `hexal` | hexal-forge-1.18.2-0.1.14.jar | 135 |
| `blockcarpentry` | blockcarpentry-1.18-0.5.1.jar | 134 |
| `dyenamics` | dyenamics-2.0.0.jar | 127 |
| `controlengineering` | ControlEngineering-0.1.1.jar | 124 |
| `darkutils` | DarkUtilities-Forge-1.18.2-10.1.7.jar | 124 |
| `simplylight` | simplylight-1.18.2-1.4.5-build.43.jar | 124 |
| `skyblockbuilder` | SkyblockBuilder-1.18.2-3.3.33.jar | 122 |
| `resourcify` | Resourcify (1.18.2-forge)-1.3.0.jar | 118 |
| `vaultlootbeams` | VaultLootBeams-1.18.2-1.0.2.jar | 118 |
| `storagedrawers` | StorageDrawers-1.18.2-10.2.1.jar | 109 |
| `thermal_extra` | ThermalExtra 1.18.2-2.0.3.jar | 109 |
| `cloudstorage` | cloudstorage-1.1.0-1.18.2.jar | 108 |
| `pehkui` | Pehkui-3.7.11+1.18.2-forge.jar | 104 |
| `integratedcrafting` | IntegratedCrafting-1.18.2-1.1.6.jar | 103 |
| `mcwlights` | mcw-lights-1.0.6-mc1.18.2forge.jar | 102 |
| `factory_blocks` | factory-blocks-mod-1.0.1+1.18.2.jar | 101 |

## 三、有中文但不完整（补漏即可）

这些模组**自带部分中文**，缺的是剩下的。补译时必须**以自带 `zh_cn` 为底**再叠加，否则会把已有中文整片顶掉。

| 命名空间 | 模组 jar | 英文键 | 自带中文 | 缺键 | 伪翻译 | 待译 |
|---|---|---|---|---|---|---|
| `occultism` | occultism-1.18.2-1.84.0.jar | 1471 | 801 | 697 | 3 | 663 |
| `integrateddynamics` | IntegratedDynamics-1.18.2-1.17.4.jar | 1643 | 1275 | 537 | 30 | 567 |
| `grimoireofgaia` | GrimoireOfGaia4-1.18.2-2.0.0-beta.13.jar | 841 | 841 | 0 | 459 | 459 |
| `lightmanscurrency` | lightmanscurrency-1.18.2-2.1.2.5e.jar | 1103 | 671 | 448 | 12 | 458 |
| `ftbquests` | ftb-quests-forge-1802.3.15-build.298.jar | 459 | 204 | 300 | 11 | 310 |
| `dungeons_mobs` | dungeons_mobs-1.18.2-3.0.2-beta.jar | 442 | 160 | 300 | 0 | 299 |
| `architects_palette` | Architects-Palette-1.18.2-1.3.2.1.jar | 528 | 230 | 298 | 0 | 297 |
| `fancymenu` | fancymenu_forge_3.7.0_MC_1.18.2.jar | 1800 | 1586 | 214 | 33 | 247 |
| `botania` | Botania-1.18.2-435.jar | 3259 | 3141 | 125 | 88 | 213 |
| `railways` | Steam_Rails-1.4.8+forge-mc1.18.2-build.23.jar | 349 | 145 | 210 | 0 | 209 |
| `draconicevolution` | Draconic-Evolution-1.18.2-3.0.31.531-universal.jar | 728 | 611 | 154 | 7 | 160 |
| `infernalmobs` | infernalmobs-1.18.6.jar | 177 | 177 | 0 | 142 | 142 |
| `framedblocks` | FramedBlocks-5.11.5.jar | 247 | 106 | 141 | 0 | 140 |
| `ae2` | appliedenergistics2-forge-11.7.6.jar | 943 | 857 | 93 | 9 | 101 |
| `mcwtrpdoors` | mcw-trapdoors-1.1.2-mc1.18.2forge.jar | 187 | 89 | 98 | 0 | 98 |
| `immersiveengineering` | ImmersiveEngineering-1.18.2-8.4.0-161.jar | 1335 | 1299 | 36 | 56 | 92 |
| `xaerominimap` | Xaeros_Minimap_25.2.10_Forge_1.18.2.jar | 611 | 533 | 83 | 1 | 84 |
| `integratedtunnels` | IntegratedTunnels-1.18.2-1.8.19.jar | 483 | 410 | 83 | 0 | 83 |
| `quark` | Quark-3.2-358.jar | 1096 | 1030 | 66 | 15 | 81 |
| `toms_storage` | toms_storage-1.18.2-1.4.4.jar | 135 | 53 | 83 | 2 | 81 |
| `tropicraft` | Tropicraft-9.4.1-release+707-gha.jar | 537 | 488 | 56 | 16 | 72 |
| `industrialforegoing` | industrial-foregoing-1.18.2-3.3.1.6-10.jar | 583 | 529 | 68 | 2 | 70 |
| `cfm` | cfm-7.0.0-pre35-1.18.2.jar | 497 | 497 | 0 | 68 | 68 |
| `sodium` | embeddium-0.2.16+mc1.18.2.jar | 68 | 4 | 64 | 0 | 64 |
| `fairylights` | fairylights-5.0.0-1.18.2.jar | 83 | 65 | 59 | 0 | 58 |
| `hostilenetworks` | HostileNeuralNetworks-1.18.2-3.3.0.jar | 158 | 105 | 53 | 4 | 57 |
| `jei` | jei-1.18.2-forge-10.2.1.1006.jar | 155 | 118 | 38 | 14 | 52 |
| `lootr` | lootr-forge-1.18.2-0.3.29.71.jar | 51 | 51 | 0 | 49 | 48 |
| `createaddition` | createaddition-1.18.2-1.0.0.jar | 223 | 213 | 44 | 1 | 44 |
| `mcwdoors` | mcw-doors-1.1.0forge-mc1.18.2.jar | 233 | 189 | 44 | 0 | 44 |
| `naturalist` | naturalist-forge-1.1.1-1.18.2.jar | 139 | 137 | 2 | 41 | 43 |
| `ars_nouveau` | ars_nouveau-1.18.2-2.9.0.jar | 1081 | 1044 | 38 | 3 | 41 |
| `itemfilters` | item-filters-forge-1802.2.8-build.50.jar | 43 | 1 | 43 | 0 | 41 |
| `refinedstorage` | refinedstorage-1.10.6.jar | 361 | 349 | 35 | 6 | 40 |
| `configured` | configured-2.0.1-1.18.2.jar | 65 | 64 | 1 | 38 | 39 |
| `modularrouters` | modular-routers-1.18.2-9.1.2.jar | 355 | 326 | 34 | 4 | 37 |
| `buildinggadgets` | buildinggadgets-3.13.2-build.21+mc1.18.2.jar | 188 | 234 | 8 | 23 | 31 |
| `controllable` | controllable-0.17.0-1.18.2.jar | 201 | 185 | 16 | 15 | 31 |
| `waystones` | waystones-forge-1.18.2-10.2.2.jar | 146 | 144 | 2 | 29 | 31 |
| `createdieselgenerators` | createdieselgenerators-1.18.2-1.2h.jar | 139 | 112 | 27 | 2 | 29 |
| … | 其余 84 个见 `vendor-scan.json` | | | | | |

## 四、AE 系专项体检（点名模组）

| 命名空间 | 模组 jar | 英文键 | 自带中文 | 覆盖率 | 待译 | 状态 |
|---|---|---|---|---|---|---|
| `ae2` | appliedenergistics2-forge-11.7.6.jar | 943 | 857 | 91% | 101 | ⚠️ 不完整 |
| `ae2additions` | AEAdditions-1.18.2-3.2.8.jar | 68 | 0 | 0% | 67 | ❌ 零中文 |
| `ae2things` | AE2-Things-1.0.5.jar | 17 | 0 | 0% | 16 | ❌ 零中文 |
| `aeinfinitybooster` | AEInfinityBooster-1.18.2-1.1.0+9.jar | 3 | 0 | 0% | 2 | ❌ 零中文 |
| `ae2insertexportcard` | ae2insertexportcard-1.18.2-1.0.0.jar | 5 | 5 | 100% | 0 | ✅ 已完整 |
| `appmek` | Applied-Mekanistics-1.2.2.jar | 16 | 0 | 0% | 15 | ❌ 零中文 |
| `appbot` | Applied-Botanics-1.0.3.jar | 22 | 0 | 0% | 21 | ❌ 零中文 |
| `appliedcooking` | appliedcooking-1.0.3.jar | 7 | 0 | 0% | 6 | ❌ 零中文 |
| `megacells` | MEGACells-1.4.2-1.18.2.jar | 52 | 0 | 0% | 51 | ❌ 零中文 |
| `merequester` | merequester-1.18.2-1.1.2.jar | 21 | 21 | 100% | 0 | ✅ 已完整 |

**AE 系合计待译 279 条。**

> 说明：`ae2` 本体（appliedenergistics2）**自带 857 键中文、覆盖率 91%**，并不是「没汉化」——它缺的是 93 个键 + 9 条伪翻译。真正整包零中文的是 `ae2additions` 等生态模组。所以「AE 没汉化」的体感，大多来自**AE 的附属模组**和**页签/物品名的分散缺口**，不是本体的锅。


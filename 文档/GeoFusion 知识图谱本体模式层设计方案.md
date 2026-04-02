# GeoFusion 知识图谱本体模式层设计方案

## "灾害 – 数据 – 算法"三元协同本体模型

---

## 0 设计总纲

### 0.1 设计哲学

本体模型围绕 **"灾害驱动需求、数据满足需求、算法处理数据"** 这一核心逻辑链，将三元要素通过 **工作流模式层 (Workflow Pattern Layer)** 桥接为有机整体。三元协同的本质含义：

```text
灾害 (Disaster)          数据 (Data)            算法 (Algorithm)
  ──提出需求──▶  ◀──满足需求──  ◀──处理能力──
       │                │                │
       │    triggers     │   requires     │   uses
       ▼                ▼                ▼
     ╔══════════════════════════════════════╗
     ║   工作流模式层 (Workflow Pattern)     ║
     ║   ── 三元协同的枢纽与实例化桥梁 ──    ║
     ╚══════════════════════════════════════╝
```

### 0.2 命名空间定义

| 前缀  | IRI | 说明  |
| --- | --- | --- |
| `gf:` | `http://geofusion.org/ontology#` | GeoFusion 核心本体 |
| `geo:` | `http://www.opengis.net/ont/geosparql#` | OGC GeoSPARQL |
| `time:` | `http://www.w3.org/2006/time#` | W3C OWL-Time |
| `prov:` | `http://www.w3.org/ns/prov#` | W3C PROV-O 溯源 |
| `skos:` | `http://www.w3.org/2004/02/skos/core#` | SKOS 概念体系 |
| `qudt:` | `http://qudt.org/schema/qudt/` | 量与单位 |
| `owl:` | `http://www.w3.org/2002/07/owl#` | OWL 本体语言 |
| `rdfs:` | `http://www.w3.org/2000/01/rdf-schema#` | RDF Schema |
| `xsd:` | `http://www.w3.org/2001/XMLSchema#` | XML Schema 数据类型 |

### 0.3 四层架构概览

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 4: 场景描述层 (Scenario Layer) — 灾害元                        │
│   DisasterEvent · DisasterType · SpatialExtent · TemporalExtent     │
│   SeverityLevel · ResponsePhase · DataNeed · ImpactArea             │
├────────────────────────┬────────────────────────────────────────────┤
│                   triggers / requiresDataTheme                      │
├────────────────────────▼────────────────────────────────────────────┤
│ Layer 3: 工作流模式层 (Workflow Pattern Layer) — 三元协同桥梁         │
│   WorkflowPattern · StepTemplate · WorkflowInstance · StepInstance  │
│   ExecutionLog · RepairRecord                                       │
├────────────────────────┬────────────────────────────────────────────┤
│          usesAlgorithm / requiresData                               │
├──────────┬─────────────┴─────────────┬──────────────────────────────┤
│ Layer 2  │                           │ Layer 1                      │
│ 算法描述层 (Algorithm Layer)          │ 数据描述层 (Data Layer)       │
│   Algorithm · TransformOp            │ DataSource · DataType        │
│   InputSpec · OutputSpec             │ DataFormat · CRS · Theme     │
│   Condition · Task                   │ GeometryType · QualityProfile│
│   ToolImplementation                 │ AttributeSchema              │
└──────────┴───────────────────────────┴──────────────────────────────┘
```

---

## 0.4 MVP工程落地硬约束（2026-03）

为对齐当前工程实现，补充以下执行约束：

1. 首版输入仅支持 `zip shapefile`，并要求最小文件集 `.shp/.shx/.dbf`。  
2. 首版融合范围仅含 **建筑矢量** 与 **道路矢量**。  
3. 融合算法实现必须复用 `Algorithm/build.py`、`Algorithm/line.py`，禁止重写算法本体；允许工程化封装（输入输出参数化、CRS参数化、异常包装、日志）。  
4. 算法调用不得依赖脚本 `__main__` 中的硬编码路径，统一通过适配器层调用函数链。  
5. 首版交付以 Web/API 作业化服务为目标，KG/LLM 全量推理留作后续扩展。

## 0.5 MVP算法映射（建筑/道路）

| 融合对象 | 本体中的能力单元 | 复用脚本 | 工程适配入口 | 输出产物 |
| --- | --- | --- | --- | --- |
| 建筑融合 | `WorkflowPattern + usesAlgorithm` | `Algorithm/build.py` | `adapters/building_adapter.py` | `fused_buildings.shp` |
| 道路融合 | `WorkflowPattern + usesAlgorithm` | `Algorithm/line.py` | `adapters/road_adapter.py` | `fused_roads.shp` |

---

## 1 Layer 1：数据描述层 (Data Layer) — 数据元

### 1.1 核心类定义

#### 1.1.1 `gf:DataSource` — 数据源

> **语义**：一个具体的地理数据提供者或数据集，如"Geofabrik OSM 导出"、"Microsoft Building Footprints"、"HydroSHEDS HydroRIVERS" 等。

| 数据属性 | 类型  | 约束  | 说明  |
| --- | --- | --- | --- |
| `gf:sourceId` | `xsd:string` | **必填**，唯一 | 数据源全局标识符 |
| `gf:sourceName` | `xsd:string` | **必填** | 人类可读名称 |
| `gf:sourceDescription` | `xsd:string` | 可选  | 自然语言描述（供LLM理解） |
| `gf:accessEndpoint` | `xsd:anyURI` | 可选  | 下载/API 入口URL |
| `gf:accessProtocol` | `xsd:string` | 可选  | HTTP/FTP/WFS/WMS/API等 |
| `gf:license` | `xsd:string` | 可选  | 许可协议 (ODbL/CC-BY/…) |
| `gf:isActive` | `xsd:boolean` | 默认true | 当前是否可用 |
| `gf:lastChecked` | `xsd:dateTime` | 可选  | 最后可用性检查时间 |

| 对象属性 | 值域  | 基数  | 说明  |
| --- | --- | --- | --- |
| `gf:hasFormat` | `gf:DataFormat` | 1..\* | 原始数据格式 |
| `gf:hasCRS` | `gf:CRS` | 1..\* | 使用的坐标参考系 |
| `gf:hasTheme` | `gf:Theme` | 1..\* | 数据主题分类 |
| `gf:hasCoverage` | `gf:SpatialExtent` | 1..1 | 空间覆盖范围 |
| `gf:hasQuality` | `gf:QualityProfile` | 0..1 | 质量画像 |
| `gf:hasUpdateFrequency` | `gf:TemporalFrequency` | 0..1 | 更新频率 |
| `gf:provides` | `gf:DataType` | 1..\* | **核心关系**：提供何种数据类型 |

#### 1.1.2 `gf:DataType` — 数据类型（抽象语义类型）

> **语义**：对地理数据进行抽象语义描述，不依赖于具体数据源。如"面状建筑物轮廓数据"、"线状水系数据"、"点状兴趣点数据"等。这是三元协同中**连接数据源与算法的关键抽象层**。

| 数据属性 | 类型  | 约束  | 说明  |
| --- | --- | --- | --- |
| `gf:typeId` | `xsd:string` | **必填**，唯一 | 类型全局标识符 |
| `gf:typeLabel` | `xsd:string` | **必填** | 人类可读标签 |
| `gf:typeDescription` | `xsd:string` | 可选  | 语义描述（供LLM/向量检索） |

| 对象属性 | 值域  | 基数  | 说明  |
| --- | --- | --- | --- |
| `gf:hasGeometryType` | `gf:GeometryType` | 1..1 | 几何类型 |
| `gf:hasTheme` | `gf:Theme` | 1..\* | 所属主题 |
| `gf:hasAttributeSchema` | `gf:AttributeSchema` | 0..\* | 期望包含的属性模式 |
| `gf:canTransformTo` | `gf:DataType` | 0..\* | **关键关系**：可转换到另一类型 |
| `gf:isProvidedBy` | `gf:DataSource` | 0..\* | 反向关系：由哪些源提供 |

> `gf:canTransformTo` **关系的复杂结构**：由于转换涉及具体操作和代价，使用**关系类 (Reified Relationship)** `gf:TransformationPath` 来描述：

```turtle
gf:TransformationPath a owl:Class ;
    rdfs:subClassOf [
        owl:onProperty gf:fromDataType ; owl:cardinality 1 ;
    ] , [
        owl:onProperty gf:toDataType ; owl:cardinality 1 ;
    ] .

gf:fromDataType  a owl:ObjectProperty ; rdfs:domain gf:TransformationPath ; rdfs:range gf:DataType .
gf:toDataType    a owl:ObjectProperty ; rdfs:domain gf:TransformationPath ; rdfs:range gf:DataType .
gf:viaTransform  a owl:ObjectProperty ; rdfs:domain gf:TransformationPath ; rdfs:range gf:TransformOp .
gf:transformCost a owl:DatatypeProperty ; rdfs:domain gf:TransformationPath ; rdfs:range xsd:float .
gf:qualityLoss   a owl:DatatypeProperty ; rdfs:domain gf:TransformationPath ; rdfs:range xsd:float .
```

#### 1.1.3 `gf:DataFormat` — 数据格式（枚举类）

```turtle
gf:DataFormat a owl:Class ;
    owl:equivalentClass [
        owl:oneOf (
            gf:Shapefile gf:GeoJSON gf:GeoTIFF gf:CSV
            gf:OSM_PBF gf:GML gf:WKT gf:GeoParquet
            gf:KML gf:GPKG gf:NetCDF gf:JSON
        )
    ] .
```

| 数据属性 | 类型  | 说明  |
| --- | --- | --- |
| `gf:formatName` | `xsd:string` | 格式名称 |
| `gf:mimeType` | `xsd:string` | MIME类型 |
| `gf:isVector` | `xsd:boolean` | 是否为矢量格式 |
| `gf:isRaster` | `xsd:boolean` | 是否为栅格格式 |
| `gf:supportsStreaming` | `xsd:boolean` | 是否支持流式读取 |

#### 1.1.4 `gf:CRS` — 坐标参考系

```turtle
gf:CRS a owl:Class .
# 预定义实例
gf:EPSG_4326  a gf:CRS ; gf:epsgCode 4326  ; gf:crsName "WGS 84" ;
    gf:isGeographic true ; gf:unit "degree" .
gf:EPSG_3857  a gf:CRS ; gf:epsgCode 3857  ; gf:crsName "Web Mercator" ;
    gf:isGeographic false ; gf:unit "meter" .
gf:EPSG_32643 a gf:CRS ; gf:epsgCode 32643 ; gf:crsName "UTM Zone 43N" ;
    gf:isGeographic false ; gf:unit "meter" .
```

#### 1.1.5 `gf:GeometryType` — 几何类型（枚举类）

```turtle
gf:GeometryType a owl:Class ;
    owl:equivalentClass [
        owl:oneOf (
            gf:Point gf:MultiPoint gf:LineString gf:MultiLineString
            gf:Polygon gf:MultiPolygon gf:Raster gf:GeometryCollection
        )
    ] .
```

| 对象属性 | 值域  | 说明  |
| --- | --- | --- |
| `gf:canGeneralizedTo` | `gf:GeometryType` | 几何类型降维关系，如 Polygon → Point (质心) |

#### 1.1.6 `gf:Theme` — 主题分类

> 使用 SKOS 概念体系组织，支持层级关系。

```turtle
gf:Theme rdfs:subClassOf skos:Concept .

gf:Infrastructure a gf:Theme ; skos:prefLabel "基础设施" .
  gf:Building      a gf:Theme ; skos:broader gf:Infrastructure ; skos:prefLabel "建筑" .
  gf:Transportation a gf:Theme ; skos:broader gf:Infrastructure ; skos:prefLabel "交通" .
    gf:Road         a gf:Theme ; skos:broader gf:Transportation ; skos:prefLabel "道路" .
    gf:Railway      a gf:Theme ; skos:broader gf:Transportation ; skos:prefLabel "铁路" .
    gf:Airport      a gf:Theme ; skos:broader gf:Transportation ; skos:prefLabel "机场" .
  gf:EnergyFacility a gf:Theme ; skos:broader gf:Infrastructure ; skos:prefLabel "能源设施" .

gf:NaturalFeature  a gf:Theme ; skos:prefLabel "自然地物" .
  gf:Hydrology     a gf:Theme ; skos:broader gf:NaturalFeature ; skos:prefLabel "水系" .
  gf:Elevation     a gf:Theme ; skos:broader gf:NaturalFeature ; skos:prefLabel "地形高程" .

gf:AdminBoundary   a gf:Theme ; skos:prefLabel "行政区划" .
gf:POI             a gf:Theme ; skos:prefLabel "兴趣点" .
gf:SocialFacility  a gf:Theme ; skos:prefLabel "社会设施" .
  gf:Education     a gf:Theme ; skos:broader gf:SocialFacility ; skos:prefLabel "教育" .
  gf:Healthcare    a gf:Theme ; skos:broader gf:SocialFacility ; skos:prefLabel "医疗" .
gf:Population      a gf:Theme ; skos:prefLabel "人口" .
gf:LandUse         a gf:Theme ; skos:prefLabel "土地利用" .
```

#### 1.1.7 `gf:QualityProfile` — 数据质量画像

> **语义**：依据开题报告中的六维质量检验体系，对数据源的质量进行结构化描述。

| 数据属性 | 类型  | 值域  | 说明  |
| --- | --- | --- | --- |
| `gf:completeness` | `xsd:float` | [0, 1] | 完整性 |
| `gf:positionalAccuracy` | `xsd:float` | ≥ 0 (米) | 位置精度 |
| `gf:attributeAccuracy` | `xsd:float` | [0, 1] | 属性准确性 |
| `gf:temporalCurrency` | `xsd:string` | —   | 时效性描述 |
| `gf:logicalConsistency` | `xsd:float` | [0, 1] | 逻辑一致性 |
| `gf:overallScore` | `xsd:float` | [0, 1] | 综合质量得分 |
| `gf:assessmentDate` | `xsd:dateTime` | —   | 评估日期 |
| `gf:assessmentMethod` | `xsd:string` | —   | 评估方法 |

#### 1.1.8 `gf:AttributeSchema` — 属性模式

> **语义**：描述某种DataType期望拥有的属性结构（Schema-level，非Instance-level）。

| 数据属性 | 类型  | 说明  |
| --- | --- | --- |
| `gf:attributeName` | `xsd:string` | 属性名 |
| `gf:attributeType` | `xsd:string` | 数据类型 (string/float/int/datetime/json) |
| `gf:isRequired` | `xsd:boolean` | 是否必须 |
| `gf:valueRange` | `xsd:string` | 值域描述 |
| `gf:semanticLabel` | `xsd:string` | 语义标签（供LLM理解） |

#### 1.1.9 `gf:TemporalFrequency` — 更新频率（枚举类）

```turtle
gf:TemporalFrequency a owl:Class ;
    owl:equivalentClass [
        owl:oneOf (
            gf:RealTime gf:Hourly gf:Daily gf:Weekly
            gf:Monthly gf:Quarterly gf:Annually gf:Irregular gf:Static
        )
    ] .
```

### 1.2 Layer 1 完整类图

```text
gf:DataSource ────provides────▶ gf:DataType ────hasGeometryType────▶ gf:GeometryType
    │                               │
    ├── hasFormat ──▶ gf:DataFormat  ├── hasTheme ──▶ gf:Theme (skos:Concept)
    ├── hasCRS ──▶ gf:CRS           ├── hasAttributeSchema ──▶ gf:AttributeSchema
    ├── hasTheme ──▶ gf:Theme        └── canTransformTo ──▶ gf:DataType
    ├── hasCoverage ──▶ gf:SpatialExtent         │  (via gf:TransformationPath)
    ├── hasQuality ──▶ gf:QualityProfile
    └── hasUpdateFrequency ──▶ gf:TemporalFrequency
```

---

## 2 Layer 2：算法描述层 (Algorithm Layer) — 算法元

### 2.1 核心类定义

#### 2.1.1 `gf:Task` — 任务类型（语义分类）

> **语义**：地理数据处理中的抽象任务类型，是算法的语义分类依据，也是 LLM 将自然语言需求映射到算法的关键中间层。

```turtle
gf:Task a owl:Class .

# 一级任务分类
gf:DataAcquisition    a gf:Task ; skos:prefLabel "数据获取" .
gf:DataPreprocessing  a gf:Task ; skos:prefLabel "数据预处理" .
gf:DataTransformation a gf:Task ; skos:prefLabel "数据转换" .
gf:SpatialAnalysis    a gf:Task ; skos:prefLabel "空间分析" .
gf:EntityAlignment    a gf:Task ; skos:prefLabel "实体对齐" .
gf:DataFusion         a gf:Task ; skos:prefLabel "数据融合" .
gf:QualityAssessment  a gf:Task ; skos:prefLabel "质量评估" .
gf:Visualization      a gf:Task ; skos:prefLabel "可视化输出" .

# 二级任务分类（示例）
gf:CRSTransform       a gf:Task ; skos:broader gf:DataTransformation ; skos:prefLabel "坐标系转换" .
gf:FormatConversion   a gf:Task ; skos:broader gf:DataTransformation ; skos:prefLabel "格式转换" .
gf:GeometryRepair     a gf:Task ; skos:broader gf:DataPreprocessing ; skos:prefLabel "几何修复" .
gf:GeometryCleaning   a gf:Task ; skos:broader gf:DataPreprocessing ; skos:prefLabel "几何清洗" .
gf:AttributeStandard  a gf:Task ; skos:broader gf:DataPreprocessing ; skos:prefLabel "属性标准化" .
gf:SpatialClipping    a gf:Task ; skos:broader gf:DataPreprocessing ; skos:prefLabel "空间裁剪" .
gf:DuplicateDetection a gf:Task ; skos:broader gf:DataPreprocessing ; skos:prefLabel "重复检测" .
gf:BufferAnalysis     a gf:Task ; skos:broader gf:SpatialAnalysis ; skos:prefLabel "缓冲区分析" .
gf:OverlayAnalysis    a gf:Task ; skos:broader gf:SpatialAnalysis ; skos:prefLabel "叠加分析" .
gf:SpatialJoin        a gf:Task ; skos:broader gf:SpatialAnalysis ; skos:prefLabel "空间连接" .
gf:ProximityAnalysis  a gf:Task ; skos:broader gf:SpatialAnalysis ; skos:prefLabel "邻近分析" .
gf:FloodExtentExtract a gf:Task ; skos:broader gf:SpatialAnalysis ; skos:prefLabel "洪水淹没范围提取" .
gf:SpatialMatching    a gf:Task ; skos:broader gf:EntityAlignment ; skos:prefLabel "空间匹配" .
gf:SemanticMatching   a gf:Task ; skos:broader gf:EntityAlignment ; skos:prefLabel "语义匹配" .
gf:MultiSourceMerge   a gf:Task ; skos:broader gf:DataFusion ; skos:prefLabel "多源合并" .
gf:ConflictResolution a gf:Task ; skos:broader gf:DataFusion ; skos:prefLabel "冲突消解" .
```

#### 2.1.2 `gf:Algorithm` — 地理处理算法

> **语义**：一个具体的、可执行的地理处理算法或工具。是三元协同中**连接数据与灾害需求的处理能力单元**。

| 数据属性 | 类型  | 约束  | 说明  |
| --- | --- | --- | --- |
| `gf:algoId` | `xsd:string` | **必填**，唯一 | 算法全局标识符 |
| `gf:algoName` | `xsd:string` | **必填** | 人类可读名称 |
| `gf:algoDescription` | `xsd:string` | **必填** | 自然语言功能描述（供LLM理解与RAG检索） |
| `gf:complexity` | `xsd:string` | 可选  | 计算复杂度 O(n), O(n²) 等 |
| `gf:successRate` | `xsd:float` | [0,1]，默认0.5 | 历史执行成功率（自修复学习更新） |
| `gf:avgExecTime` | `xsd:float` | ≥ 0 (秒) | 平均执行耗时 |
| `gf:version` | `xsd:string` | 可选  | 版本号 |

| 对象属性 | 值域  | 基数  | 说明  |
| --- | --- | --- | --- |
| `gf:solves` | `gf:Task` | 1..\* | **核心关系**：解决何种任务 |
| `gf:hasInputSpec` | `gf:InputSpec` | 1..\* | 输入规格（支持多输入端口） |
| `gf:hasOutputSpec` | `gf:OutputSpec` | 1..\* | 输出规格 |
| `gf:hasPrecondition` | `gf:Condition` | 0..\* | 前置条件 |
| `gf:hasPostcondition` | `gf:Condition` | 0..\* | 后置条件 |
| `gf:alternativeTo` | `gf:Algorithm` | 0..\* | **关键关系**：可替代算法（自修复） |
| `gf:hasImplementation` | `gf:ToolImplementation` | 1..\* | 具体工具实现 |
| `gf:supersedes` | `gf:Algorithm` | 0..\* | 取代旧版本算法 |

> `gf:alternativeTo` **的语义约束** (OWL 公理)：

```turtle
# alternativeTo 是对称的（A可替代B意味着B也可替代A）
gf:alternativeTo a owl:SymmetricProperty .

# alternativeTo 的两端必须解决相同类型的Task
# (SHACL约束，无法直接用OWL表达)
# ∀ a1, a2: alternativeTo(a1, a2) → ∃ t: solves(a1, t) ∧ solves(a2, t)
```

#### 2.1.3 `gf:ToolImplementation` — 工具实现

> **语义**：将抽象算法与可执行代码/工具绑定。同一 Algorithm 可以有多种实现（如 Python函数、ArcPy 工具、GDAL命令）。

| 数据属性 | 类型  | 说明  |
| --- | --- | --- |
| `gf:toolPath` | `xsd:string` | 可执行路径/模块.函数名 |
| `gf:toolType` | `xsd:string` | Python / CLI / WPS / REST |
| `gf:containerImage` | `xsd:string` | Docker 镜像（若需隔离执行） |
| `gf:parameterTemplate` | `xsd:string` (JSON) | 默认参数模板 |
| `gf:dependencies` | `xsd:string` | 依赖库列表 |

#### 2.1.4 `gf:InputSpec` / `gf:OutputSpec` — 输入/输出规格

> **语义**：形式化描述算法的数据接口契约，是 **V(tᵢ) 验证函数** 和 **数据流连通性检查** 的核心依据。

`gf:InputSpec`：

| 属性  | 类型  | 说明  |
| --- | --- | --- |
| `gf:portName` | `xsd:string` | 输入端口名（如 "primary\_input", "secondary\_input"） |
| `gf:portOrder` | `xsd:int` | 端口序号 |
| `gf:expectedDataType` | → `gf:DataType` | 期望的语义数据类型 |
| `gf:expectedGeometry` | → `gf:GeometryType` | 期望的几何类型 |
| `gf:expectedCRS` | → `gf:CRS` | 期望的坐标系 |
| `gf:expectedFormat` | → `gf:DataFormat` | 期望的数据格式（可选） |
| `gf:requiredAttributes` | `xsd:string` (JSON array) | 必须包含的属性名列表 |
| `gf:isOptional` | `xsd:boolean` | 是否可选输入 |
| `gf:acceptsMultiple` | `xsd:boolean` | 是否接受多个数据集输入 |

`gf:OutputSpec`：

| 属性  | 类型  | 说明  |
| --- | --- | --- |
| `gf:portName` | `xsd:string` | 输出端口名 |
| `gf:outputDataType` | → `gf:DataType` | 输出的语义数据类型 |
| `gf:outputGeometry` | → `gf:GeometryType` | 输出的几何类型 |
| `gf:outputCRS` | → `gf:CRS` | 输出的坐标系 |
| `gf:outputFormat` | → `gf:DataFormat` | 输出的数据格式 |
| `gf:producedAttributes` | `xsd:string` (JSON array) | 输出包含的属性 |

#### 2.1.5 `gf:TransformOp` — 数据转换操作

> **语义**：一种特殊的算法，专门用于数据类型/格式/坐标系之间的转换。是 `gf:Algorithm` 的子类。

```turtle
gf:TransformOp rdfs:subClassOf gf:Algorithm .
```

| 额外属性 | 类型  | 说明  |
| --- | --- | --- |
| `gf:fromDataType` | → `gf:DataType` | 源数据类型 |
| `gf:toDataType` | → `gf:DataType` | 目标数据类型 |
| `gf:fromFormat` | → `gf:DataFormat` | 源格式 |
| `gf:toFormat` | → `gf:DataFormat` | 目标格式 |
| `gf:fromCRS` | → `gf:CRS` | 源坐标系 |
| `gf:toCRS` | → `gf:CRS` | 目标坐标系 |
| `gf:transformCost` | `xsd:float` | 转换代价 (归一化，0-1) |
| `gf:qualityLoss` | `xsd:float` | 精度损失 (归一化，0-1) |
| `gf:isLossless` | `xsd:boolean` | 是否无损转换 |

#### 2.1.6 `gf:Condition` — 前置/后置条件

> **语义**：形式化的断言条件，用于工作流验证阶段 (Stage 3) 的前置/后置条件一致性检查。

| 数据属性 | 类型  | 说明  |
| --- | --- | --- |
| `gf:conditionId` | `xsd:string` | 条件唯一标识 |
| `gf:conditionType` | `xsd:string` | 条件类型（见下表） |
| `gf:expression` | `xsd:string` | 形式化表达式 |
| `gf:description` | `xsd:string` | 自然语言描述（供LLM理解） |
| `gf:isCritical` | `xsd:boolean` | 是否为硬性约束（不满足则必须修复） |

**条件类型枚举**：

| conditionType | 含义  | expression 示例 |
| --- | --- | --- |
| `crs_match` | 坐标系必须匹配 | `input.crs == EPSG:4326` |
| `geom_type_match` | 几何类型必须匹配 | `input.geom_type == Polygon` |
| `attr_exists` | 必须包含某属性 | `'height' in input.attributes` |
| `attr_range` | 属性值域检查 | `input.confidence >= 0.5` |
| `spatial_overlap` | 空间覆盖必须重叠 | `ST_Intersects(input.bbox, $roi)` |
| `format_match` | 格式必须匹配 | `input.format == GeoJSON` |
| `geometry_valid` | 几何必须有效 | `ST_IsValid(input.geometry)` |
| `not_empty` | 数据集不能为空 | `input.count > 0` |
| `temporal_within` | 时间范围约束 | `input.timestamp >= $start_time` |

### 2.2 Layer 2 完整类图

```text
gf:Task ◀──solves── gf:Algorithm ──hasImplementation──▶ gf:ToolImplementation
                         │
                         ├── hasInputSpec ──▶ gf:InputSpec
                         │                       ├── expectedDataType ──▶ gf:DataType (Layer 1)
                         │                       ├── expectedGeometry ──▶ gf:GeometryType
                         │                       └── expectedCRS ──▶ gf:CRS
                         │
                         ├── hasOutputSpec ──▶ gf:OutputSpec
                         │                       ├── outputDataType ──▶ gf:DataType (Layer 1)
                         │                       └── ...
                         │
                         ├── hasPrecondition ──▶ gf:Condition
                         ├── hasPostcondition ──▶ gf:Condition
                         ├── alternativeTo ──▶ gf:Algorithm (对称)
                         │
                         └── [子类] gf:TransformOp
                                     ├── fromDataType ──▶ gf:DataType
                                     └── toDataType ──▶ gf:DataType
```

---

## 3 Layer 3：工作流模式层 (Workflow Pattern Layer) — 三元协同桥梁

### 3.1 设计理念

工作流模式层是三元协同的**核心枢纽**。它通过以下方式桥接三元：

```text
灾害元 ──triggers──▶ WorkflowPattern ──hasStep──▶ StepTemplate
                                                     │
                                           ┌─────────┴─────────┐
                                           │                   │
                                  usesAlgorithm(算法元)   requiresData(数据元)
```

工作流模式层同时存在\*\*模式层 (Schema)**和**实例层 (Instance)\*\*两个层次：

-   **WorkflowPattern / StepTemplate**：可复用的流程骨架（模式层）
    
-   **WorkflowInstance / StepInstance**：某次具体执行的实例（实例层）
    

### 3.2 核心类定义

#### 3.2.1 `gf:WorkflowPattern` — 工作流模式（可复用骨架）

> **语义**：一个经过验证的、可复用的地理数据融合工作流骨架，描述了在特定场景下应按何种顺序组合哪些算法处理哪些数据。这是 **KG 骨架检索 (Stage 1)** 的核心查询对象。

| 数据属性 | 类型  | 约束  | 说明  |
| --- | --- | --- | --- |
| `gf:patternId` | `xsd:string` | **必填**，唯一 | 模式全局标识 |
| `gf:patternName` | `xsd:string` | **必填** | 模式名称（如"洪水建筑损毁评估工作流"） |
| `gf:patternDescription` | `xsd:string` | **必填** | 自然语言描述（供LLM检索与理解） |
| `gf:successRate` | `xsd:float` | [0,1]，自动更新 | 历史执行成功率 |
| `gf:avgExecTime` | `xsd:float` | ≥ 0 (秒) | 历史平均执行耗时 |
| `gf:usageCount` | `xsd:int` | ≥ 0 | 被使用次数 |
| `gf:createdAt` | `xsd:dateTime` | 自动生成 | 创建时间 |
| `gf:lastUsedAt` | `xsd:dateTime` | 自动更新 | 最后使用时间 |
| `gf:isVerified` | `xsd:boolean` | 默认false | 是否经专家验证 |
| `gf:patternVersion` | `xsd:string` | 可选  | 版本号 |

| 对象属性 | 值域  | 基数  | 说明  |
| --- | --- | --- | --- |
| `gf:appliesTo` | `gf:ScenarioType` | 1..\* | 适用场景类型 |
| `gf:hasStep` | `gf:StepTemplate` | 1..\* (有序) | 步骤模板序列 |
| `gf:requiresTheme` | `gf:Theme` | 1..\* | 需要哪些主题的数据 |
| `gf:producesOutput` | `gf:DataType` | 1..\* | 最终输出的数据类型 |
| `gf:derivedFrom` | `gf:WorkflowPattern` | 0..\* | 从哪个模式演化而来 |
| `prov:wasGeneratedBy` | —   | 0..1 | 生成来源（专家/LLM/经验学习） |

#### 3.2.2 `gf:ScenarioType` — 场景类型

> **语义**：对灾害场景的类型化抽象，是 WorkflowPattern 与 DisasterEvent 之间的类型桥梁。

| 数据属性 | 类型  | 说明  |
| --- | --- | --- |
| `gf:scenarioId` | `xsd:string` | 场景类型标识 |
| `gf:scenarioName` | `xsd:string` | 如"洪水灾后建筑损毁评估"、"洪水淹没范围分析" |
| `gf:scenarioDescription` | `xsd:string` | 自然语言描述 |

| 对象属性 | 值域  | 说明  |
| --- | --- | --- |
| `gf:forDisasterType` | `gf:DisasterType` | 对应的灾害类型 |
| `gf:forResponsePhase` | `gf:ResponsePhase` | 对应的响应阶段 |
| `gf:needsTheme` | `gf:Theme` | 此场景需要的数据主题 |

#### 3.2.3 `gf:StepTemplate` — 步骤模板

> **语义**：WorkflowPattern 中的一个步骤模板，描述"在此步骤中，用什么算法处理什么类型的数据"。是三元协同在单步粒度上的体现。

| 数据属性 | 类型  | 约束  | 说明  |
| --- | --- | --- | --- |
| `gf:stepOrder` | `xsd:int` | **必填** | 步骤在模式中的序号 |
| `gf:stepName` | `xsd:string` | **必填** | 步骤名称 |
| `gf:stepDescription` | `xsd:string` | 可选  | 自然语言描述 |
| `gf:isOptional` | `xsd:boolean` | 默认false | 是否可跳过 |
| `gf:defaultParameters` | `xsd:string` (JSON) | 可选  | 默认参数 |
| `gf:estimatedTime` | `xsd:float` | ≥ 0 | 预估耗时(秒) |

| 对象属性 | 值域  | 基数  | 说明  |
| --- | --- | --- | --- |
| `gf:usesAlgorithm` | `gf:Algorithm` | 1..1 | **算法元绑定** |
| `gf:requiresDataType` | `gf:DataType` | 1..\* | **数据元绑定**（需要什么类型的数据） |
| `gf:preferredSource` | `gf:DataSource` | 0..\* | 推荐的数据源 |
| `gf:dependsOnStep` | `gf:StepTemplate` | 0..\* | 步骤依赖关系（DAG） |
| `gf:belongsToPattern` | `gf:WorkflowPattern` | 1..1 | 所属工作流模式 |
| `gf:producesDataType` | `gf:DataType` | 1..\* | 输出的数据类型 |

> **关键约束**：StepTemplate 的 `requiresDataType` 必须与其 `usesAlgorithm` 的 `InputSpec.expectedDataType` 兼容。这就是 V(tᵢ) 验证函数的检查内容。

#### 3.2.4 `gf:WorkflowInstance` — 工作流实例

> **语义**：某次具体执行的工作流。由 WorkflowPattern 实例化而来，绑定了具体的数据源和参数。

| 数据属性 | 类型  | 说明  |
| --- | --- | --- |
| `gf:instanceId` | `xsd:string` | 实例唯一标识 (UUID) |
| `gf:triggerType` | `xsd:string` | 触发类型: user\_query / disaster\_event / scheduled / data\_update |
| `gf:triggerContent` | `xsd:string` | 触发内容描述 |
| `gf:status` | `xsd:string` | pending / running / completed / failed / repaired |
| `gf:startTime` | `xsd:dateTime` | 开始执行时间 |
| `gf:endTime` | `xsd:dateTime` | 结束时间 |
| `gf:totalDuration` | `xsd:float` | 总耗时(秒) |
| `gf:repairCount` | `xsd:int` | 修复次数 |
| `gf:planJSON` | `xsd:string` (JSON) | LLM 生成的完整工作流计划 |

| 对象属性 | 值域  | 说明  |
| --- | --- | --- |
| `gf:instantiatesPattern` | `gf:WorkflowPattern` | 基于哪个工作流模式 |
| `gf:hasStepInstance` | `gf:StepInstance` | 包含的步骤实例 |
| `gf:triggeredByEvent` | `gf:DisasterEvent` | 触发此实例的灾害事件（可选） |
| `gf:hasSpatialContext` | `gf:SpatialExtent` | 空间范围上下文 |
| `gf:hasTemporalContext` | `gf:TemporalExtent` | 时间范围上下文 |

#### 3.2.5 `gf:StepInstance` — 步骤实例

| 数据属性 | 类型  | 说明  |
| --- | --- | --- |
| `gf:stepInstanceId` | `xsd:string` | 实例标识 |
| `gf:actualParameters` | `xsd:string` (JSON) | 实际执行参数 |
| `gf:stepStatus` | `xsd:string` | pending / running / success / failed / skipped / repaired |
| `gf:stepStartTime` | `xsd:dateTime` | 步骤开始时间 |
| `gf:stepEndTime` | `xsd:dateTime` | 步骤结束时间 |
| `gf:errorMessage` | `xsd:string` | 若失败，错误信息 |
| `gf:isTransformStep` | `xsd:boolean` | 是否为自动插入的转换步骤 |
| `gf:kgValidated` | `xsd:boolean` | V(tᵢ) 验证结果 |

| 对象属性 | 值域  | 说明  |
| --- | --- | --- |
| `gf:instantiatesStep` | `gf:StepTemplate` | 基于哪个步骤模板 |
| `gf:actualAlgorithm` | `gf:Algorithm` | 实际使用的算法（可能因修复而与模板不同） |
| `gf:actualDataSource` | `gf:DataSource` | 实际使用的数据源 |
| `gf:inputArtifact` | `gf:DataArtifact` | 实际输入数据制品 |
| `gf:outputArtifact` | `gf:DataArtifact` | 实际输出数据制品 |

#### 3.2.6 `gf:DataArtifact` — 数据制品

> **语义**：工作流执行过程中产生的中间/最终数据实体（物理文件或数据库表）。

| 数据属性 | 类型  | 说明  |
| --- | --- | --- |
| `gf:artifactId` | `xsd:string` | 制品标识 |
| `gf:storagePath` | `xsd:anyURI` | 物理存储路径 |
| `gf:recordCount` | `xsd:int` | 记录数 |
| `gf:fileSize` | `xsd:long` | 文件大小(字节) |
| `gf:createdAt` | `xsd:dateTime` | 创建时间 |

| 对象属性 | 值域  | 说明  |
| --- | --- | --- |
| `gf:hasDataType` | `gf:DataType` | 语义数据类型 |
| `gf:hasFormat` | `gf:DataFormat` | 实际格式 |
| `gf:hasCRS` | `gf:CRS` | 实际坐标系 |
| `gf:hasCoverage` | `gf:SpatialExtent` | 实际空间范围 |
| `prov:wasGeneratedBy` | `gf:StepInstance` | 由哪个步骤生成 |
| `prov:wasDerivedFrom` | `gf:DataArtifact` | 由哪个制品派生 |

#### 3.2.7 `gf:ExecutionLog` — 执行日志

| 数据属性 | 类型  | 说明  |
| --- | --- | --- |
| `gf:logId` | `xsd:string` | 日志标识 |
| `gf:logLevel` | `xsd:string` | INFO / WARN / ERROR / FATAL |
| `gf:logMessage` | `xsd:string` | 日志消息 |
| `gf:logTimestamp` | `xsd:dateTime` | 时间戳 |

| 对象属性 | 值域  | 说明  |
| --- | --- | --- |
| `gf:belongsToInstance` | `gf:WorkflowInstance` | 所属工作流实例 |
| `gf:belongsToStep` | `gf:StepInstance` | 所属步骤实例 |

#### 3.2.8 `gf:RepairRecord` — 修复记录

> **语义**：记录自修复过程，是**执行后学习 (L3)** 的数据基础。

| 数据属性 | 类型  | 说明  |
| --- | --- | --- |
| `gf:repairId` | `xsd:string` | 修复记录标识 |
| `gf:failureType` | `xsd:string` | DataSourceUnavailable / AlgorithmFailed / DataIncompatible / Timeout |
| `gf:failureDetail` | `xsd:string` | 失败详情 |
| `gf:repairStrategy` | `xsd:string` | alternative\_source / alternative\_algorithm / transform\_insert / llm\_replan |
| `gf:repairSuccess` | `xsd:boolean` | 修复是否成功 |
| `gf:repairTimestamp` | `xsd:dateTime` | 修复时间 |

| 对象属性 | 值域  | 说明  |
| --- | --- | --- |
| `gf:repairedStep` | `gf:StepInstance` | 被修复的步骤 |
| `gf:originalAlgorithm` | `gf:Algorithm` | 原始失败算法 |
| `gf:replacementAlgorithm` | `gf:Algorithm` | 替代算法 |
| `gf:originalSource` | `gf:DataSource` | 原始失败数据源 |
| `gf:replacementSource` | `gf:DataSource` | 替代数据源 |
| `gf:insertedTransform` | `gf:TransformOp` | 插入的转换操作 |

### 3.3 Layer 3 完整类图

```text
gf:WorkflowPattern ──hasStep──▶ gf:StepTemplate
      │                              │
      ├── appliesTo ▶ ScenarioType   ├── usesAlgorithm ──▶ gf:Algorithm (Layer 2)
      ├── requiresTheme ▶ Theme      ├── requiresDataType ──▶ gf:DataType (Layer 1)
      ├── producesOutput ▶ DataType  ├── preferredSource ──▶ gf:DataSource (Layer 1)
      └── derivedFrom ▶ self         ├── dependsOnStep ──▶ gf:StepTemplate
                                     └── producesDataType ──▶ gf:DataType
      │
      │ instantiatesPattern
      ▼
gf:WorkflowInstance ──hasStepInstance──▶ gf:StepInstance
      │                                      │
      ├── triggeredByEvent ▶ DisasterEvent   ├── actualAlgorithm ──▶ gf:Algorithm
      ├── hasSpatialContext ▶ SpatialExtent  ├── actualDataSource ──▶ gf:DataSource
      └── hasTemporalContext ▶ TemporalExt   ├── inputArtifact ──▶ gf:DataArtifact
                                             ├── outputArtifact ──▶ gf:DataArtifact
                                             └── [logged by] ──▶ gf:ExecutionLog
                                                                  gf:RepairRecord
```

---

## 4 Layer 4：场景描述层 (Scenario Layer) — 灾害元

### 4.1 核心类定义

#### 4.1.1 `gf:DisasterType` — 灾害类型（枚举+层级）

```turtle
gf:DisasterType a owl:Class .

# 一级分类
gf:MeteorologicalDisaster a gf:DisasterType ; skos:prefLabel "气象灾害" .
gf:GeologicalDisaster     a gf:DisasterType ; skos:prefLabel "地质灾害" .
gf:HydrologicalDisaster   a gf:DisasterType ; skos:prefLabel "水文灾害" .

# 二级分类
gf:Flood      a gf:DisasterType ; skos:broader gf:HydrologicalDisaster ; skos:prefLabel "洪水" .
gf:FlashFlood a gf:DisasterType ; skos:broader gf:Flood ; skos:prefLabel "山洪" .
gf:RiverFlood a gf:DisasterType ; skos:broader gf:Flood ; skos:prefLabel "河流洪水" .
gf:UrbanFlood a gf:DisasterType ; skos:broader gf:Flood ; skos:prefLabel "城市内涝" .
gf:Earthquake a gf:DisasterType ; skos:broader gf:GeologicalDisaster ; skos:prefLabel "地震" .
gf:Typhoon    a gf:DisasterType ; skos:broader gf:MeteorologicalDisaster ; skos:prefLabel "台风" .
gf:Landslide  a gf:DisasterType ; skos:broader gf:GeologicalDisaster ; skos:prefLabel "滑坡" .
gf:Wildfire   a gf:DisasterType ; skos:broader gf:MeteorologicalDisaster ; skos:prefLabel "森林火灾" .
```

#### 4.1.2 `gf:DisasterEvent` — 灾害事件实例

> **语义**：一次具体的灾害事件，是三元协同的**触发起点**。灾害事件产生数据需求，数据需求驱动工作流模式检索。

| 数据属性 | 类型  | 约束  | 说明  |
| --- | --- | --- | --- |
| `gf:eventId` | `xsd:string` | **必填**，唯一 | 事件标识 |
| `gf:eventName` | `xsd:string` | **必填** | 如"河南7·20特大暴雨" |
| `gf:eventDescription` | `xsd:string` | 可选  | 事件描述 |
| `gf:eventStartTime` | `xsd:dateTime` | **必填** | 开始时间 |
| `gf:eventEndTime` | `xsd:dateTime` | 可选  | 结束时间 |
| `gf:alertSource` | `xsd:string` | 可选  | 预警来源 |
| `gf:estimatedAffectedPop` | `xsd:int` | 可选  | 估计影响人口 |

| 对象属性 | 值域  | 基数  | 说明  |
| --- | --- | --- | --- |
| `gf:hasType` | `gf:DisasterType` | 1..1 | 灾害类型 |
| `gf:hasSpatialExtent` | `gf:SpatialExtent` | 1..1 | 影响范围 |
| `gf:hasTemporalExtent` | `gf:TemporalExtent` | 1..1 | 时间范围 |
| `gf:hasSeverity` | `gf:SeverityLevel` | 1..1 | 严重程度 |
| `gf:hasResponsePhase` | `gf:ResponsePhase` | 1..1 | 当前响应阶段 |
| `gf:hasDataNeed` | `gf:DataNeed` | 1..\* | **关键关系**：产生的数据需求 |
| `gf:triggers` | `gf:WorkflowPattern` | 0..\* | **核心三元关系**：触发工作流 |
| `gf:hasImpactArea` | `gf:ImpactArea` | 0..\* | 影响区域详情 |

#### 4.1.3 `gf:SeverityLevel` — 严重程度（枚举类）

```turtle
gf:SeverityLevel a owl:Class ;
    owl:equivalentClass [
        owl:oneOf (
            gf:L1_Minor gf:L2_Moderate gf:L3_Severe
            gf:L4_Extreme gf:L5_Catastrophic
        )
    ] .

gf:L1_Minor        a gf:SeverityLevel ; gf:severityValue 1 ; skos:prefLabel "轻微" .
gf:L2_Moderate     a gf:SeverityLevel ; gf:severityValue 2 ; skos:prefLabel "中等" .
gf:L3_Severe       a gf:SeverityLevel ; gf:severityValue 3 ; skos:prefLabel "严重" .
gf:L4_Extreme      a gf:SeverityLevel ; gf:severityValue 4 ; skos:prefLabel "特别严重" .
gf:L5_Catastrophic a gf:SeverityLevel ; gf:severityValue 5 ; skos:prefLabel "灾难性" .
```

#### 4.1.4 `gf:ResponsePhase` — 应急响应阶段

```turtle
gf:ResponsePhase a owl:Class ;
    owl:equivalentClass [
        owl:oneOf (
            gf:Preparedness gf:EarlyWarning gf:ImmediateResponse
            gf:Relief gf:Recovery gf:Reconstruction
        )
    ] .

gf:Preparedness       a gf:ResponsePhase ; gf:phaseOrder 1 ; skos:prefLabel "备灾" .
gf:EarlyWarning       a gf:ResponsePhase ; gf:phaseOrder 2 ; skos:prefLabel "预警" .
gf:ImmediateResponse  a gf:ResponsePhase ; gf:phaseOrder 3 ; skos:prefLabel "应急响应" .
gf:Relief             a gf:ResponsePhase ; gf:phaseOrder 4 ; skos:prefLabel "救援" .
gf:Recovery           a gf:ResponsePhase ; gf:phaseOrder 5 ; skos:prefLabel "恢复" .
gf:Reconstruction     a gf:ResponsePhase ; gf:phaseOrder 6 ; skos:prefLabel "重建" .
```

#### 4.1.5 `gf:DataNeed` — 数据需求

> **语义**：灾害事件在特定响应阶段对数据的具体需求。是连接**灾害元**与**数据元**的桥梁类。

| 数据属性 | 类型  | 说明  |
| --- | --- | --- |
| `gf:needId` | `xsd:string` | 需求标识 |
| `gf:needDescription` | `xsd:string` | 自然语言描述 |
| `gf:priority` | `xsd:int` | 优先级 (1-5, 1最高) |
| `gf:isFullfilled` | `xsd:boolean` | 是否已满足 |

| 对象属性 | 值域  | 说明  |
| --- | --- | --- |
| `gf:needsTheme` | `gf:Theme` | 需要的数据主题 |
| `gf:needsDataType` | `gf:DataType` | 需要的数据类型 |
| `gf:needsSpatialExtent` | `gf:SpatialExtent` | 需要的空间范围 |
| `gf:needsTemporalExtent` | `gf:TemporalExtent` | 需要的时间范围 |
| `gf:needsMinQuality` | `gf:QualityProfile` | 最低质量要求 |
| `gf:forPhase` | `gf:ResponsePhase` | 对应的响应阶段 |
| `gf:canBeSatisfiedBy` | `gf:DataSource` | 能满足此需求的数据源 |

#### 4.1.6 `gf:SpatialExtent` — 空间范围

| 数据属性 | 类型  | 说明  |
| --- | --- | --- |
| `gf:bboxWKT` | `xsd:string` | WKT 格式的边界框 |
| `gf:minLon` | `xsd:float` | 最小经度 |
| `gf:maxLon` | `xsd:float` | 最大经度 |
| `gf:minLat` | `xsd:float` | 最小纬度 |
| `gf:maxLat` | `xsd:float` | 最大纬度 |
| `gf:areaKm2` | `xsd:float` | 面积(平方公里) |
| `geo:asWKT` | `geo:wktLiteral` | GeoSPARQL 标准几何 |

| 对象属性 | 值域  | 说明  |
| --- | --- | --- |
| `gf:withinAdmin` | `gf:AdminRegion` | 所属行政区 |

#### 4.1.7 `gf:TemporalExtent` — 时间范围

```turtle
gf:TemporalExtent rdfs:subClassOf time:ProperInterval .
```

| 数据属性 | 类型  | 说明  |
| --- | --- | --- |
| `time:hasBeginning` | `xsd:dateTime` | 开始时间 |
| `time:hasEnd` | `xsd:dateTime` | 结束时间 |
| `gf:duration` | `xsd:duration` | 持续时长 |

#### 4.1.8 `gf:ImpactArea` — 影响区域

| 数据属性 | 类型  | 说明  |
| --- | --- | --- |
| `gf:impactId` | `xsd:string` | 影响区域标识 |
| `gf:impactLevel` | `xsd:string` | 影响程度 (heavy/moderate/light) |
| `gf:floodDepth` | `xsd:float` | 洪水淹没深度(米)——洪水场景特有 |

| 对象属性 | 值域  | 说明  |
| --- | --- | --- |
| `gf:hasExtent` | `gf:SpatialExtent` | 空间范围 |
| `gf:affectsTheme` | `gf:Theme` | 影响涉及的主题 |

### 4.2 Layer 4 完整类图

```text
gf:DisasterEvent
    ├── hasType ──▶ gf:DisasterType (层级结构)
    ├── hasSpatialExtent ──▶ gf:SpatialExtent
    ├── hasTemporalExtent ──▶ gf:TemporalExtent
    ├── hasSeverity ──▶ gf:SeverityLevel
    ├── hasResponsePhase ──▶ gf:ResponsePhase
    ├── hasDataNeed ──▶ gf:DataNeed
    │                      ├── needsTheme ──▶ gf:Theme (→ Layer 1)
    │                      ├── needsDataType ──▶ gf:DataType (→ Layer 1)
    │                      └── canBeSatisfiedBy ──▶ gf:DataSource (→ Layer 1)
    ├── hasImpactArea ──▶ gf:ImpactArea
    └── triggers ──▶ gf:WorkflowPattern (→ Layer 3)
```

---

## 5 三元协同关系全景图

### 5.1 跨层关系总表

| #   | 关系名称 | 起点 (Domain) | 终点 (Range) | 跨层  | 语义  | 协同用途 |
| --- | --- | --- | --- | --- | --- | --- |
| R01 | `provides` | DataSource | DataType | L1→L1 | 数据源提供某数据类型 | 数据可用性检查 |
| R02 | `canTransformTo` | DataType | DataType | L1→L1 | 数据类型间转换路径 | 不兼容时自动修复 |
| R03 | `hasInputSpec` | Algorithm | InputSpec | L2→L2 | 算法输入规格 | V(tᵢ)验证 |
| R04 | `hasOutputSpec` | Algorithm | OutputSpec | L2→L2 | 算法输出规格 | 数据流连通性 |
| R05 | `solves` | Algorithm | Task | L2→L2 | 算法解决的任务 | LLM候选算法检索 |
| R06 | `alternativeTo` | Algorithm | Algorithm | L2→L2 | 可替代关系(对称) | **自修复核心** |
| R07 | `expectedDataType` | InputSpec | DataType | **L2→L1** | 算法期望的数据类型 | **数据-算法协同** |
| R08 | `outputDataType` | OutputSpec | DataType | **L2→L1** | 算法产出的数据类型 | **数据-算法协同** |
| R09 | `usesAlgorithm` | StepTemplate | Algorithm | **L3→L2** | 步骤使用的算法 | **工作流-算法协同** |
| R10 | `requiresDataType` | StepTemplate | DataType | **L3→L1** | 步骤需要的数据类型 | **工作流-数据协同** |
| R11 | `preferredSource` | StepTemplate | DataSource | **L3→L1** | 步骤推荐数据源 | 数据源选择 |
| R12 | `appliesTo` | WorkflowPattern | ScenarioType | **L3→L4** | 模式适用场景 | **工作流-灾害协同** |
| R13 | `triggers` | DisasterEvent | WorkflowPattern | **L4→L3** | 灾害触发工作流 | **灾害-工作流协同** |
| R14 | `hasDataNeed` | DisasterEvent | DataNeed | L4→L4 | 灾害产生的数据需求 | 需求分析 |
| R15 | `needsDataType` | DataNeed | DataType | **L4→L1** | 数据需求指向数据类型 | **灾害-数据协同** |
| R16 | `canBeSatisfiedBy` | DataNeed | DataSource | **L4→L1** | 能满足需求的数据源 | **灾害-数据协同** |
| R17 | `forDisasterType` | ScenarioType | DisasterType | L4→L4 | 场景对应灾害类型 | 场景分类 |
| R18 | `hasPrecondition` | Algorithm | Condition | L2→L2 | 算法前置条件 | 形式化验证 |
| R19 | `hasPostcondition` | Algorithm | Condition | L2→L2 | 算法后置条件 | 形式化验证 |
| R20 | `instantiatesPattern` | WorkflowInstance | WorkflowPattern | L3→L3 | 实例化关系 | 执行追踪 |

### 5.2 三元协同路径图

```text
                        ╔═══════════════╗
                        ║   灾害事件     ║
                        ║ DisasterEvent ║
                        ╚═══════╤═══════╝
                                │
            ┌───────────────────┼────────────────────┐
            │ hasDataNeed       │ triggers            │ hasSeverity
            ▼                   ▼                     ▼
     ╔══════════════╗   ╔═══════════════╗    ╔════════════════╗
     ║  数据需求     ║   ║  工作流模式    ║    ║  严重程度       ║
     ║  DataNeed    ║   ║  Workflow-    ║    ║  SeverityLevel ║
     ╚══════╤═══════╝   ║  Pattern     ║    ╚════════════════╝
            │           ╚═══════╤═══════╝
            │ needsDataType     │ hasStep
            │                   │
            ▼                   ▼
     ╔══════════════╗   ╔═══════════════╗
     ║  数据类型     ║   ║  步骤模板      ║
     ║  DataType    ║◀──║  StepTemplate ║
     ╚══════╤═══════╝   ╚═══╤═══╤═══════╝
            │                │   │
            │ isProvidedBy   │   │ usesAlgorithm
            │                │   │
            ▼                │   ▼
     ╔══════════════╗        │  ╔═══════════════╗
     ║  数据源       ║        │  ║   算法         ║
     ║  DataSource  ║◀───────┘  ║  Algorithm    ║
     ╚══════════════╝           ╚═══════╤═══════╝
       preferredSource                  │
                                        │ alternativeTo (对称)
                                        ▼
                                 ╔═══════════════╗
                                 ║  替代算法       ║
                                 ║  Algorithm    ║
                                 ╚═══════════════╝
```

### 5.3 V(tᵢ) 验证路径在图谱中的表达

```text
V(tᵢ) 验证函数的 KG 查询路径：

给定步骤 tᵢ = (dᵢ, aᵢ)，即 StepInstance 绑定了 DataType dᵢ 和 Algorithm aᵢ

路径1（直接兼容）：
  (dᵢ:DataType)◀─expectedDataType─(spec:InputSpec)◀─hasInputSpec─(aᵢ:Algorithm)
  ⇒ V(tᵢ) = 1

路径2（经转换兼容）：
  (dᵢ:DataType)─canTransformTo─▶(d':DataType)◀─expectedDataType─(spec:InputSpec)◀─hasInputSpec─(aᵢ:Algorithm)
  ⇒ V(tᵢ) = 1, 同时自动插入 TransformOp 步骤

路径3（不可达）：
  不存在从 dᵢ 到 aᵢ 的 InputSpec 的任何路径
  ⇒ V(tᵢ) = 0

Cypher 查询实现：
```

```cypher
// V(tᵢ) 验证查询
MATCH (d:DataType {typeId: $dataTypeId})
MATCH (a:Algorithm {algoId: $algoId})-[:hasInputSpec]->(spec:InputSpec)

// 路径1: 直接兼容
OPTIONAL MATCH direct = (d)<-[:expectedDataType]-(spec)

// 路径2: 经转换兼容 (最多3跳)
OPTIONAL MATCH transform_path = (d)-[:canTransformTo*1..3]->(d2:DataType)<-[:expectedDataType]-(spec)

WITH d, a, spec, direct, transform_path,
     CASE
       WHEN direct IS NOT NULL THEN 1
       WHEN transform_path IS NOT NULL THEN 1
       ELSE 0
     END AS v_score,
     CASE
       WHEN direct IS NOT NULL THEN 'direct'
       WHEN transform_path IS NOT NULL THEN 'via_transform'
       ELSE 'incompatible'
     END AS match_type

RETURN v_score, match_type, transform_path
```

---

## 6 OWL 公理与约束 (SHACL)

### 6.1 OWL 公理

```turtle
# 1. alternativeTo 是对称属性
gf:alternativeTo a owl:SymmetricProperty .

# 2. canTransformTo 是传递属性（转换可以链式传递，但需限制深度）
#    注意：OWL 中传递性会导致推理开销，在Neo4j实现中用路径查询控制深度
gf:canTransformTo a owl:TransitiveProperty .

# 3. DataSource 必须至少提供一种 DataType
gf:DataSource rdfs:subClassOf [
    a owl:Restriction ;
    owl:onProperty gf:provides ;
    owl:minCardinality 1
] .

# 4. Algorithm 必须至少有一个 InputSpec
gf:Algorithm rdfs:subClassOf [
    a owl:Restriction ;
    owl:onProperty gf:hasInputSpec ;
    owl:minCardinality 1
] .

# 5. Algorithm 必须至少有一个 OutputSpec
gf:Algorithm rdfs:subClassOf [
    a owl:Restriction ;
    owl:onProperty gf:hasOutputSpec ;
    owl:minCardinality 1
] .

# 6. WorkflowPattern 必须至少有一个 StepTemplate
gf:WorkflowPattern rdfs:subClassOf [
    a owl:Restriction ;
    owl:onProperty gf:hasStep ;
    owl:minCardinality 1
] .

# 7. StepTemplate 必须绑定一个 Algorithm
gf:StepTemplate rdfs:subClassOf [
    a owl:Restriction ;
    owl:onProperty gf:usesAlgorithm ;
    owl:cardinality 1
] .

# 8. DisasterEvent 必须有一个 DisasterType
gf:DisasterEvent rdfs:subClassOf [
    a owl:Restriction ;
    owl:onProperty gf:hasType ;
    owl:cardinality 1
] .

# 9. TransformOp 是 Algorithm 的子类
gf:TransformOp rdfs:subClassOf gf:Algorithm .

# 10. TransformOp 的 fromDataType 和 toDataType 不能相同
# (无法直接用 OWL 表达，通过 SHACL 约束)
```

### 6.2 SHACL 约束规则

```turtle
@prefix sh: <http://www.w3.org/ns/shacl#> .

# 约束1: alternativeTo 两端必须解决相同类型的 Task
gf:AlternativeToTaskConsistencyShape a sh:NodeShape ;
    sh:targetClass gf:Algorithm ;
    sh:sparql [
        sh:message "alternativeTo的两个算法必须解决至少一个相同的Task" ;
        sh:select """
            SELECT $this ?alt
            WHERE {
                $this gf:alternativeTo ?alt .
                FILTER NOT EXISTS {
                    $this gf:solves ?t .
                    ?alt gf:solves ?t .
                }
            }
        """ ;
    ] .

# 约束2: StepTemplate 的 requiresDataType 必须与 usesAlgorithm 的 InputSpec 兼容
gf:StepDataAlgoConsistencyShape a sh:NodeShape ;
    sh:targetClass gf:StepTemplate ;
    sh:sparql [
        sh:message "StepTemplate的requiresDataType必须与Algorithm的InputSpec兼容" ;
        sh:select """
            SELECT $this ?reqDT ?expDT
            WHERE {
                $this gf:requiresDataType ?reqDT .
                $this gf:usesAlgorithm ?algo .
                ?algo gf:hasInputSpec ?spec .
                ?spec gf:expectedDataType ?expDT .
                FILTER (?reqDT != ?expDT)
                FILTER NOT EXISTS {
                    ?reqDT gf:canTransformTo* ?expDT .
                }
            }
        """ ;
    ] .

# 约束3: WorkflowPattern 步骤顺序无环 (DAG)
gf:StepDAGShape a sh:NodeShape ;
    sh:targetClass gf:StepTemplate ;
    sh:sparql [
        sh:message "StepTemplate的依赖关系不能形成环" ;
        sh:select """
            SELECT $this
            WHERE {
                $this gf:dependsOnStep+ $this .
            }
        """ ;
    ] .

# 约束4: TransformOp 的源类型和目标类型不能相同
gf:TransformOpDifferentTypesShape a sh:NodeShape ;
    sh:targetClass gf:TransformOp ;
    sh:property [
        sh:path gf:fromDataType ;
        sh:minCount 1 ; sh:maxCount 1 ;
    ] ;
    sh:sparql [
        sh:message "TransformOp的fromDataType和toDataType不能相同" ;
        sh:select """
            SELECT $this
            WHERE {
                $this gf:fromDataType ?from .
                $this gf:toDataType ?to .
                FILTER (?from = ?to)
            }
        """ ;
    ] .

# 约束5: 质量评分值域
gf:QualityProfileShape a sh:NodeShape ;
    sh:targetClass gf:QualityProfile ;
    sh:property [
        sh:path gf:completeness ;
        sh:minInclusive 0.0 ; sh:maxInclusive 1.0 ;
        sh:datatype xsd:float ;
    ] ;
    sh:property [
        sh:path gf:positionalAccuracy ;
        sh:minInclusive 0.0 ;
        sh:datatype xsd:float ;
    ] ;
    sh:property [
        sh:path gf:overallScore ;
        sh:minInclusive 0.0 ; sh:maxInclusive 1.0 ;
        sh:datatype xsd:float ;
    ] .

# 约束6: SeverityLevel 值域
gf:SeverityLevelShape a sh:NodeShape ;
    sh:targetClass gf:SeverityLevel ;
    sh:property [
        sh:path gf:severityValue ;
        sh:minInclusive 1 ; sh:maxInclusive 5 ;
        sh:datatype xsd:int ;
    ] .
```

---

## 7 Neo4j 图模式实现

### 7.1 节点标签映射

| OWL 类 | Neo4j 标签 | 说明  |
| --- | --- | --- |
| `gf:DataSource` | `:DataSource` | 数据源节点 |
| `gf:DataType` | `:DataType` | 数据类型节点 |
| `gf:DataFormat` | `:DataFormat` | 数据格式节点 |
| `gf:CRS` | `:CRS` | 坐标系节点 |
| `gf:Theme` | `:Theme` | 主题节点 |
| `gf:GeometryType` | `:GeometryType` | 几何类型节点 |
| `gf:QualityProfile` | `:QualityProfile` | 质量画像节点 |
| `gf:Algorithm` | `:Algorithm` | 算法节点 |
| `gf:TransformOp` | `:Algorithm:TransformOp` (双标签) | 转换操作节点 |
| `gf:Task` | `:Task` | 任务类型节点 |
| `gf:InputSpec` | `:InputSpec` | 输入规格节点 |
| `gf:OutputSpec` | `:OutputSpec` | 输出规格节点 |
| `gf:Condition` | `:Condition` | 条件节点 |
| `gf:ToolImplementation` | `:ToolImpl` | 工具实现节点 |
| `gf:WorkflowPattern` | `:WorkflowPattern` | 工作流模式节点 |
| `gf:StepTemplate` | `:StepTemplate` | 步骤模板节点 |
| `gf:ScenarioType` | `:ScenarioType` | 场景类型节点 |
| `gf:WorkflowInstance` | `:WorkflowInstance` | 工作流实例节点 |
| `gf:StepInstance` | `:StepInstance` | 步骤实例节点 |
| `gf:DataArtifact` | `:DataArtifact` | 数据制品节点 |
| `gf:RepairRecord` | `:RepairRecord` | 修复记录节点 |
| `gf:DisasterEvent` | `:DisasterEvent` | 灾害事件节点 |
| `gf:DisasterType` | `:DisasterType` | 灾害类型节点 |
| `gf:SeverityLevel` | `:SeverityLevel` | 严重程度节点 |
| `gf:ResponsePhase` | `:ResponsePhase` | 响应阶段节点 |
| `gf:DataNeed` | `:DataNeed` | 数据需求节点 |
| `gf:SpatialExtent` | `:SpatialExtent` | 空间范围节点 |

### 7.2 关系类型映射

| OWL 对象属性 | Neo4j 关系类型 | 属性  |
| --- | --- | --- |
| `gf:provides` | `:PROVIDES` | —   |
| `gf:canTransformTo` | `:CAN_TRANSFORM_TO` | `{cost, qualityLoss, viaOp}` |
| `gf:hasFormat` | `:HAS_FORMAT` | —   |
| `gf:hasCRS` | `:HAS_CRS` | —   |
| `gf:hasTheme` | `:HAS_THEME` | —   |
| `gf:hasCoverage` | `:HAS_COVERAGE` | —   |
| `gf:hasQuality` | `:HAS_QUALITY` | —   |
| `gf:solves` | `:SOLVES` | —   |
| `gf:hasInputSpec` | `:HAS_INPUT_SPEC` | —   |
| `gf:hasOutputSpec` | `:HAS_OUTPUT_SPEC` | —   |
| `gf:hasPrecondition` | `:HAS_PRECONDITION` | —   |
| `gf:hasPostcondition` | `:HAS_POSTCONDITION` | —   |
| `gf:alternativeTo` | `:ALTERNATIVE_TO` | `{weight, lastValidated}` |
| `gf:hasImplementation` | `:HAS_IMPL` | —   |
| `gf:expectedDataType` | `:EXPECTS_DATATYPE` | —   |
| `gf:expectedGeometry` | `:EXPECTS_GEOMETRY` | —   |
| `gf:expectedCRS` | `:EXPECTS_CRS` | —   |
| `gf:outputDataType` | `:OUTPUTS_DATATYPE` | —   |
| `gf:hasStep` | `:HAS_STEP` | `{order}` |
| `gf:usesAlgorithm` | `:USES_ALGORITHM` | —   |
| `gf:requiresDataType` | `:REQUIRES_DATATYPE` | —   |
| `gf:preferredSource` | `:PREFERRED_SOURCE` | `{priority}` |
| `gf:dependsOnStep` | `:DEPENDS_ON` | —   |
| `gf:appliesTo` | `:APPLIES_TO` | —   |
| `gf:triggers` | `:TRIGGERS` | —   |
| `gf:hasDataNeed` | `:HAS_DATA_NEED` | —   |
| `gf:needsDataType` | `:NEEDS_DATATYPE` | —   |
| `gf:hasType` | `:HAS_TYPE` | —   |
| `gf:hasSeverity` | `:HAS_SEVERITY` | —   |
| `gf:hasResponsePhase` | `:IN_PHASE` | —   |
| `gf:instantiatesPattern` | `:INSTANTIATES` | —   |
| `gf:hasStepInstance` | `:HAS_STEP_INSTANCE` | —   |
| `gf:actualAlgorithm` | `:USED_ALGORITHM` | —   |
| `gf:actualDataSource` | `:USED_SOURCE` | —   |
| `gf:inputArtifact` | `:INPUT_ARTIFACT` | —   |
| `gf:outputArtifact` | `:OUTPUT_ARTIFACT` | —   |
| `gf:repairedStep` | `:REPAIRED_STEP` | —   |
| `skos:broader` | `:BROADER` | —   |

### 7.3 Neo4j 模式创建示例

```cypher
// ==========================================
// 1. 约束与索引
// ==========================================

// 唯一性约束
CREATE CONSTRAINT ds_unique IF NOT EXISTS FOR (n:DataSource) REQUIRE n.sourceId IS UNIQUE;
CREATE CONSTRAINT dt_unique IF NOT EXISTS FOR (n:DataType) REQUIRE n.typeId IS UNIQUE;
CREATE CONSTRAINT algo_unique IF NOT EXISTS FOR (n:Algorithm) REQUIRE n.algoId IS UNIQUE;
CREATE CONSTRAINT wp_unique IF NOT EXISTS FOR (n:WorkflowPattern) REQUIRE n.patternId IS UNIQUE;
CREATE CONSTRAINT de_unique IF NOT EXISTS FOR (n:DisasterEvent) REQUIRE n.eventId IS UNIQUE;
CREATE CONSTRAINT task_unique IF NOT EXISTS FOR (n:Task) REQUIRE n.taskId IS UNIQUE;
CREATE CONSTRAINT wi_unique IF NOT EXISTS FOR (n:WorkflowInstance) REQUIRE n.instanceId IS UNIQUE;

// 全文索引（供LLM RAG检索）
CREATE FULLTEXT INDEX algo_search IF NOT EXISTS
FOR (n:Algorithm) ON EACH [n.algoName, n.algoDescription];

CREATE FULLTEXT INDEX wp_search IF NOT EXISTS
FOR (n:WorkflowPattern) ON EACH [n.patternName, n.patternDescription];

CREATE FULLTEXT INDEX ds_search IF NOT EXISTS
FOR (n:DataSource) ON EACH [n.sourceName, n.sourceDescription];

// ==========================================
// 2. 枚举节点初始化示例
// ==========================================

// 数据格式
UNWIND ['Shapefile','GeoJSON','GeoTIFF','CSV','OSM_PBF','GML','GeoParquet','KML','GPKG'] AS fmt
MERGE (f:DataFormat {name: fmt});

// CRS
MERGE (c:CRS {epsgCode: 4326, crsName: 'WGS 84', isGeographic: true, unit: 'degree'});
MERGE (c:CRS {epsgCode: 3857, crsName: 'Web Mercator', isGeographic: false, unit: 'meter'});
MERGE (c:CRS {epsgCode: 32643, crsName: 'UTM Zone 43N', isGeographic: false, unit: 'meter'});

// 几何类型
UNWIND ['Point','MultiPoint','LineString','MultiLineString','Polygon','MultiPolygon','Raster'] AS g
MERGE (gt:GeometryType {name: g});

// 灾害类型
MERGE (hy:DisasterType {name: 'HydrologicalDisaster', label: '水文灾害'})
MERGE (fl:DisasterType {name: 'Flood', label: '洪水'})-[:BROADER]->(hy)
MERGE (uf:DisasterType {name: 'UrbanFlood', label: '城市内涝'})-[:BROADER]->(fl)
MERGE (rf:DisasterType {name: 'RiverFlood', label: '河流洪水'})-[:BROADER]->(fl)
MERGE (ff:DisasterType {name: 'FlashFlood', label: '山洪'})-[:BROADER]->(fl);

// 严重程度
UNWIND [{v:1,n:'L1_Minor',l:'轻微'},{v:2,n:'L2_Moderate',l:'中等'},
        {v:3,n:'L3_Severe',l:'严重'},{v:4,n:'L4_Extreme',l:'特别严重'},
        {v:5,n:'L5_Catastrophic',l:'灾难性'}] AS s
MERGE (sl:SeverityLevel {name: s.n, value: s.v, label: s.l});

// 响应阶段
UNWIND [{o:1,n:'Preparedness',l:'备灾'},{o:2,n:'EarlyWarning',l:'预警'},
        {o:3,n:'ImmediateResponse',l:'应急响应'},{o:4,n:'Relief',l:'救援'},
        {o:5,n:'Recovery',l:'恢复'},{o:6,n:'Reconstruction',l:'重建'}] AS p
MERGE (rp:ResponsePhase {name: p.n, phaseOrder: p.o, label: p.l});

// ==========================================
// 3. 洪水场景示例数据
// ==========================================

// -- Layer 1: 数据描述层 --
// 数据类型
MERGE (dt_bld:DataType {typeId: 'DT_BuildingPolygon', typeLabel: '面状建筑物轮廓',
    typeDescription: '包含建筑物平面轮廓、高度、面积等属性的面状矢量数据'})
MERGE (dt_river:DataType {typeId: 'DT_RiverLine', typeLabel: '线状水系数据',
    typeDescription: '包含河流中心线、流量、汇水面积等属性的线状矢量数据'})
MERGE (dt_dem:DataType {typeId: 'DT_ElevationRaster', typeLabel: '高程栅格数据',
    typeDescription: '数字高程模型DEM栅格数据'})
MERGE (dt_flood_extent:DataType {typeId: 'DT_FloodExtent', typeLabel: '洪水淹没范围',
    typeDescription: '洪水淹没区域的面状矢量数据'})
MERGE (dt_damage:DataType {typeId: 'DT_DamageAssessment', typeLabel: '建筑损毁评估结果',
    typeDescription: '包含损毁等级的建筑物面状数据'});

// 几何类型绑定
MATCH (dt:DataType {typeId: 'DT_BuildingPolygon'}), (gt:GeometryType {name: 'Polygon'})
MERGE (dt)-[:HAS_GEOMETRY_TYPE]->(gt);

MATCH (dt:DataType {typeId: 'DT_RiverLine'}), (gt:GeometryType {name: 'LineString'})
MERGE (dt)-[:HAS_GEOMETRY_TYPE]->(gt);

MATCH (dt:DataType {typeId: 'DT_ElevationRaster'}), (gt:GeometryType {name: 'Raster'})
MERGE (dt)-[:HAS_GEOMETRY_TYPE]->(gt);

// 数据类型转换路径
MERGE (dt_bld)-[:CAN_TRANSFORM_TO {cost: 0.1, qualityLoss: 0.3, via: 'Centroid'}]->(dt_bld_pt:DataType {typeId: 'DT_BuildingPoint', typeLabel: '点状建筑物数据'});

// 数据源
MERGE (src_osm:DataSource {sourceId: 'SRC_Geofabrik_OSM', sourceName: 'Geofabrik OSM Export',
    sourceDescription: 'OpenStreetMap全球数据镜像', isActive: true})
MERGE (src_ms:DataSource {sourceId: 'SRC_MS_Buildings', sourceName: 'Microsoft Building Footprints',
    sourceDescription: '微软AI提取的全球建筑物轮廓', isActive: true})
MERGE (src_hydro:DataSource {sourceId: 'SRC_HydroSHEDS', sourceName: 'HydroSHEDS HydroRIVERS',
    sourceDescription: 'WWF全球水系数据集', isActive: true});

// 数据源 → 数据类型
MERGE (src_osm)-[:PROVIDES]->(dt_bld);
MERGE (src_ms)-[:PROVIDES]->(dt_bld);
MERGE (src_hydro)-[:PROVIDES]->(dt_river);

// 数据源 → 格式
MATCH (src:DataSource {sourceId: 'SRC_Geofabrik_OSM'}), (fmt:DataFormat {name: 'OSM_PBF'})
MERGE (src)-[:HAS_FORMAT]->(fmt);
MATCH (src:DataSource {sourceId: 'SRC_MS_Buildings'}), (fmt:DataFormat {name: 'GeoJSON'})
MERGE (src)-[:HAS_FORMAT]->(fmt);

// 数据源 → CRS
MATCH (src:DataSource {sourceId: 'SRC_MS_Buildings'}), (crs:CRS {epsgCode: 4326})
MERGE (src)-[:HAS_CRS]->(crs);

// 质量画像
MERGE (src_ms)-[:HAS_QUALITY]->(qp:QualityProfile {
    completeness: 0.85, positionalAccuracy: 2.0,
    attributeAccuracy: 0.9, overallScore: 0.82});

// -- Layer 2: 算法描述层 --
// 任务类型
MERGE (task_crs:Task {taskId: 'T_CRSTransform', taskName: '坐标系转换'});
MERGE (task_clean:Task {taskId: 'T_GeometryCleaning', taskName: '几何清洗'});
MERGE (task_clip:Task {taskId: 'T_SpatialClipping', taskName: '空间裁剪'});
MERGE (task_overlay:Task {taskId: 'T_OverlayAnalysis', taskName: '叠加分析'});
MERGE (task_match:Task {taskId: 'T_SpatialMatching', taskName: '空间匹配'});
MERGE (task_merge:Task {taskId: 'T_MultiSourceMerge', taskName: '多源合并'});
MERGE (task_flood:Task {taskId: 'T_FloodExtent', taskName: '洪水淹没范围提取'});
MERGE (task_damage:Task {taskId: 'T_DamageAssess', taskName: '建筑损毁评估'});

// 算法
MERGE (algo_reproject:Algorithm {algoId: 'A_Reproject', algoName: '坐标系重投影',
    algoDescription: '将地理数据从一个坐标参考系转换到另一个坐标参考系',
    successRate: 0.99, avgExecTime: 5.0})
MERGE (algo_reproject)-[:SOLVES]->(task_crs);

MERGE (algo_buffer0:Algorithm {algoId: 'A_BufferZeroRepair', algoName: 'Buffer(0)几何修复',
    algoDescription: '使用buffer(0)方法修复无效几何',
    successRate: 0.95, avgExecTime: 10.0})
MERGE (algo_buffer0)-[:SOLVES]->(task_clean);

MERGE (algo_makevalid:Algorithm {algoId: 'A_MakeValid', algoName: 'ST_MakeValid几何修复',
    algoDescription: '使用PostGIS ST_MakeValid修复无效几何',
    successRate: 0.97, avgExecTime: 8.0})
MERGE (algo_makevalid)-[:SOLVES]->(task_clean);

// alternativeTo（对称关系）
MERGE (algo_buffer0)-[:ALTERNATIVE_TO {weight: 0.8}]->(algo_makevalid);

MERGE (algo_clip:Algorithm {algoId: 'A_SpatialClip', algoName: '空间裁剪',
    algoDescription: '将数据裁剪到指定空间范围',
    successRate: 0.98, avgExecTime: 15.0})
MERGE (algo_clip)-[:SOLVES]->(task_clip);

MERGE (algo_overlay:Algorithm {algoId: 'A_Intersection', algoName: '交集叠加分析',
    algoDescription: '计算两个图层的空间交集',
    successRate: 0.96, avgExecTime: 30.0})
MERGE (algo_overlay)-[:SOLVES]->(task_overlay);

MERGE (algo_iou_match:Algorithm {algoId: 'A_IoUMatching', algoName: 'IoU空间匹配',
    algoDescription: '基于IoU(交并比)进行多源建筑物实体匹配',
    successRate: 0.88, avgExecTime: 60.0})
MERGE (algo_iou_match)-[:SOLVES]->(task_match);

MERGE (algo_hausdorff:Algorithm {algoId: 'A_HausdorffMatching', algoName: 'Hausdorff距离匹配',
    algoDescription: '基于Hausdorff距离进行几何形状匹配',
    successRate: 0.85, avgExecTime: 45.0})
MERGE (algo_hausdorff)-[:SOLVES]->(task_match);

MERGE (algo_iou_match)-[:ALTERNATIVE_TO {weight: 0.7}]->(algo_hausdorff);

// InputSpec / OutputSpec
MERGE (algo_overlay)-[:HAS_INPUT_SPEC]->(is1:InputSpec {
    portName: 'layer_a', portOrder: 1, isOptional: false, acceptsMultiple: false})
MERGE (is1)-[:EXPECTS_DATATYPE]->(dt_bld);
MERGE (is1)-[:EXPECTS_GEOMETRY]->(:GeometryType {name: 'Polygon'});
MERGE (is1)-[:EXPECTS_CRS]->(:CRS {epsgCode: 4326});

MERGE (algo_overlay)-[:HAS_INPUT_SPEC]->(is2:InputSpec {
    portName: 'layer_b', portOrder: 2, isOptional: false, acceptsMultiple: false})
MERGE (is2)-[:EXPECTS_DATATYPE]->(dt_flood_extent);

MERGE (algo_overlay)-[:HAS_OUTPUT_SPEC]->(os1:OutputSpec {portName: 'result'})
MERGE (os1)-[:OUTPUTS_DATATYPE]->(dt_damage);

// Precondition / Postcondition
MERGE (algo_overlay)-[:HAS_PRECONDITION]->(cond1:Condition {
    conditionId: 'C_CRS_Match', conditionType: 'crs_match',
    expression: 'layer_a.crs == layer_b.crs',
    description: '两个输入图层必须使用相同的坐标参考系',
    isCritical: true});

MERGE (algo_overlay)-[:HAS_PRECONDITION]->(cond2:Condition {
    conditionId: 'C_Geom_Valid', conditionType: 'geometry_valid',
    expression: 'ST_IsValid(layer_a.geometry) AND ST_IsValid(layer_b.geometry)',
    description: '两个输入图层的几何必须有效',
    isCritical: true});

MERGE (algo_overlay)-[:HAS_POSTCONDITION]->(cond3:Condition {
    conditionId: 'C_NotEmpty', conditionType: 'not_empty',
    expression: 'result.count > 0',
    description: '交集结果不能为空集',
    isCritical: false});

// TransformOp (Algorithm的子类)
MERGE (top_osm2geojson:TransformOp:Algorithm {algoId: 'T_OSM2GeoJSON',
    algoName: 'OSM PBF转GeoJSON', algoDescription: '将OSM PBF格式转为GeoJSON',
    transformCost: 0.2, qualityLoss: 0.0, isLossless: true})
MERGE (top_osm2geojson)-[:FROM_FORMAT]->(:DataFormat {name: 'OSM_PBF'})
MERGE (top_osm2geojson)-[:TO_FORMAT]->(:DataFormat {name: 'GeoJSON'});

// ToolImplementation
MERGE (algo_overlay)-[:HAS_IMPL]->(impl:ToolImpl {
    toolPath: 'geopandas.overlay', toolType: 'Python',
    parameterTemplate: '{"how": "intersection"}',
    dependencies: 'geopandas>=0.14'});

// -- Layer 3: 工作流模式层 --
// 场景类型
MERGE (scene_flood_damage:ScenarioType {
    scenarioId: 'SC_FloodBuildingDamage',
    scenarioName: '洪水灾后建筑损毁评估',
    scenarioDescription: '评估洪水事件中建筑物的损毁情况'})
MERGE (scene_flood_damage)-[:FOR_DISASTER_TYPE]->(:DisasterType {name: 'Flood'})
MERGE (scene_flood_damage)-[:FOR_RESPONSE_PHASE]->(:ResponsePhase {name: 'Relief'});

// 工作流模式
MERGE (wp:WorkflowPattern {
    patternId: 'WP_FloodBuildingDamage_v1',
    patternName: '洪水建筑损毁评估工作流',
    patternDescription: '整合多源建筑物数据与洪水淹没范围数据，通过叠加分析评估建筑损毁情况',
    successRate: 0.0, avgExecTime: 0.0, usageCount: 0,
    isVerified: false, patternVersion: '1.0'})
MERGE (wp)-[:APPLIES_TO]->(scene_flood_damage);

// 步骤模板
MERGE (wp)-[:HAS_STEP {order: 1}]->(s1:StepTemplate {
    stepOrder: 1, stepName: '建筑数据获取与格式转换',
    stepDescription: '从OSM和MS Buildings获取建筑物数据并统一为GeoJSON',
    isOptional: false, estimatedTime: 30.0})
MERGE (s1)-[:USES_ALGORITHM]->(:Algorithm {algoId: 'T_OSM2GeoJSON'})
MERGE (s1)-[:REQUIRES_DATATYPE]->(:DataType {typeId: 'DT_BuildingPolygon'})
MERGE (s1)-[:PREFERRED_SOURCE {priority: 1}]->(:DataSource {sourceId: 'SRC_MS_Buildings'})
MERGE (s1)-[:PREFERRED_SOURCE {priority: 2}]->(:DataSource {sourceId: 'SRC_Geofabrik_OSM'});

MERGE (wp)-[:HAS_STEP {order: 2}]->(s2:StepTemplate {
    stepOrder: 2, stepName: '坐标系统一',
    stepDescription: '将所有数据统一转换为WGS84坐标系',
    isOptional: false, estimatedTime: 10.0})
MERGE (s2)-[:USES_ALGORITHM]->(:Algorithm {algoId: 'A_Reproject'})
MERGE (s2)-[:DEPENDS_ON]->(s1);

MERGE (wp)-[:HAS_STEP {order: 3}]->(s3:StepTemplate {
    stepOrder: 3, stepName: '几何有效性修复',
    stepDescription: '检查并修复无效几何',
    isOptional: false, estimatedTime: 15.0})
MERGE (s3)-[:USES_ALGORITHM]->(:Algorithm {algoId: 'A_MakeValid'})
MERGE (s3)-[:DEPENDS_ON]->(s2);

MERGE (wp)-[:HAS_STEP {order: 4}]->(s4:StepTemplate {
    stepOrder: 4, stepName: '空间裁剪至灾害区域',
    stepDescription: '将数据裁剪到灾害影响范围',
    isOptional: false, estimatedTime: 20.0})
MERGE (s4)-[:USES_ALGORITHM]->(:Algorithm {algoId: 'A_SpatialClip'})
MERGE (s4)-[:DEPENDS_ON]->(s3);

MERGE (wp)-[:HAS_STEP {order: 5}]->(s5:StepTemplate {
    stepOrder: 5, stepName: '多源建筑实体匹配',
    stepDescription: '基于IoU匹配OSM和MS Buildings的重叠建筑',
    isOptional: false, estimatedTime: 60.0})
MERGE (s5)-[:USES_ALGORITHM]->(:Algorithm {algoId: 'A_IoUMatching'})
MERGE (s5)-[:DEPENDS_ON]->(s4);

MERGE (wp)-[:HAS_STEP {order: 6}]->(s6:StepTemplate {
    stepOrder: 6, stepName: '建筑与淹没范围叠加分析',
    stepDescription: '将建筑物数据与洪水淹没范围做交集叠加分析',
    isOptional: false, estimatedTime: 30.0})
MERGE (s6)-[:USES_ALGORITHM]->(:Algorithm {algoId: 'A_Intersection'})
MERGE (s6)-[:REQUIRES_DATATYPE]->(:DataType {typeId: 'DT_FloodExtent'})
MERGE (s6)-[:PRODUCES_DATATYPE]->(:DataType {typeId: 'DT_DamageAssessment'})
MERGE (s6)-[:DEPENDS_ON]->(s5);

// -- Layer 4: 场景描述层 --
// 灾害事件示例
MERGE (event:DisasterEvent {
    eventId: 'EVT_Henan_720_2021',
    eventName: '河南7·20特大暴雨',
    eventDescription: '2021年7月河南省遭遇极端强降雨引发严重洪涝灾害',
    eventStartTime: datetime('2021-07-17T00:00:00'),
    eventEndTime: datetime('2021-07-23T00:00:00'),
    alertSource: '中国气象局'})
MERGE (event)-[:HAS_TYPE]->(:DisasterType {name: 'UrbanFlood'})
MERGE (event)-[:HAS_SEVERITY]->(:SeverityLevel {name: 'L5_Catastrophic'})
MERGE (event)-[:IN_PHASE]->(:ResponsePhase {name: 'Relief'})
MERGE (event)-[:TRIGGERS]->(:WorkflowPattern {patternId: 'WP_FloodBuildingDamage_v1'});

// 数据需求
MERGE (event)-[:HAS_DATA_NEED]->(dn1:DataNeed {
    needId: 'DN_720_Building', needDescription: '郑州市区建筑物轮廓数据',
    priority: 1, isFulfilled: false})
MERGE (dn1)-[:NEEDS_DATATYPE]->(:DataType {typeId: 'DT_BuildingPolygon'})
MERGE (dn1)-[:CAN_BE_SATISFIED_BY]->(:DataSource {sourceId: 'SRC_MS_Buildings'})
MERGE (dn1)-[:CAN_BE_SATISFIED_BY]->(:DataSource {sourceId: 'SRC_Geofabrik_OSM'});

MERGE (event)-[:HAS_DATA_NEED]->(dn2:DataNeed {
    needId: 'DN_720_River', needDescription: '郑州及上游水系数据',
    priority: 2, isFulfilled: false})
MERGE (dn2)-[:NEEDS_DATATYPE]->(:DataType {typeId: 'DT_RiverLine'})
MERGE (dn2)-[:CAN_BE_SATISFIED_BY]->(:DataSource {sourceId: 'SRC_HydroSHEDS'});

// 空间范围
MERGE (event)-[:HAS_SPATIAL_EXTENT]->(se:SpatialExtent {
    minLon: 112.5, maxLon: 114.5, minLat: 34.0, maxLat: 35.5,
    areaKm2: 22000.0,
    bboxWKT: 'POLYGON((112.5 34.0, 114.5 34.0, 114.5 35.5, 112.5 35.5, 112.5 34.0))'});
```

---

## 8 类统计与完整性检查

### 8.1 类总表

| 层次  | 类名  | 类型  | 实例来源 | 数量级估计 |
| --- | --- | --- | --- | --- |
| **L1 数据描述层** | `DataSource` | 实体类 | 人工+爬取 | ~20 |
|     | `DataType` | 实体类 | 人工定义 | ~30-50 |
|     | `DataFormat` | 枚举类 | 预定义 | ~12 |
|     | `CRS` | 枚举/实体 | 预定义+按需添加 | ~10-20 |
|     | `GeometryType` | 枚举类 | 预定义 | ~7  |
|     | `Theme` | 层级枚举 | SKOS体系 | ~25-40 |
|     | `QualityProfile` | 实体类 | 评估生成 | ~20 (1:1 DataSource) |
|     | `AttributeSchema` | 实体类 | 人工定义 | ~50-100 |
|     | `TemporalFrequency` | 枚举类 | 预定义 | ~9  |
|     | `TransformationPath` | 关系类 | 人工+推理 | ~50-100 |
| **L2 算法描述层** | `Algorithm` | 实体类 | 人工注册 | ~30-60 |
|     | `TransformOp` | 实体类 (Algorithm子类) | 人工注册 | ~15-25 |
|     | `Task` | 层级枚举 | SKOS体系 | ~20-30 |
|     | `InputSpec` | 实体类 | 随Algorithm | ~60-120 |
|     | `OutputSpec` | 实体类 | 随Algorithm | ~30-60 |
|     | `Condition` | 实体类 | 人工定义 | ~40-80 |
|     | `ToolImplementation` | 实体类 | 随Algorithm | ~30-60 |
| **L3 工作流模式层** | `WorkflowPattern` | 实体类 | 专家+LLM+学习 | ~10-30 |
|     | `StepTemplate` | 实体类 | 随WorkflowPattern | ~60-180 |
|     | `ScenarioType` | 实体类 | 人工定义 | ~10-20 |
|     | `WorkflowInstance` | 实体类 | 运行时生成 | 持续增长 |
|     | `StepInstance` | 实体类 | 运行时生成 | 持续增长 |
|     | `DataArtifact` | 实体类 | 运行时生成 | 持续增长 |
|     | `ExecutionLog` | 实体类 | 运行时生成 | 持续增长 |
|     | `RepairRecord` | 实体类 | 运行时生成 | 持续增长 |
| **L4 场景描述层** | `DisasterEvent` | 实体类 | 预警信号/人工 | ~5-20 (实验阶段) |
|     | `DisasterType` | 层级枚举 | SKOS体系 | ~15-20 |
|     | `SeverityLevel` | 枚举类 | 预定义 | 5   |
|     | `ResponsePhase` | 枚举类 | 预定义 | 6   |
|     | `DataNeed` | 实体类 | 随DisasterEvent | ~20-60 |
|     | `SpatialExtent` | 实体类 | 多处引用 | ~30-50 |
|     | `TemporalExtent` | 实体类 | 多处引用 | ~20-40 |
|     | `ImpactArea` | 实体类 | 随DisasterEvent | ~10-30 |
| **合计** | **33个类** |     |     | **模式层 ~600-1200 三元组** |

### 8.2 关系总表

| #   | 关系名 | Neo4j 类型 | 起点层 → 终点层 | 属性  | 协同维度 |
| --- | --- | --- | --- | --- | --- |
| 1   | `PROVIDES` | 对象属性 | L1→L1 | —   | 数据  |
| 2   | `CAN_TRANSFORM_TO` | 对象属性 | L1→L1 | cost, qualityLoss, via | 数据  |
| 3   | `HAS_FORMAT` | 对象属性 | L1→L1 | —   | 数据  |
| 4   | `HAS_CRS` | 对象属性 | L1→L1 | —   | 数据  |
| 5   | `HAS_THEME` | 对象属性 | L1→L1 | —   | 数据  |
| 6   | `HAS_COVERAGE` | 对象属性 | L1→L4 | —   | 数据-灾害 |
| 7   | `HAS_QUALITY` | 对象属性 | L1→L1 | —   | 数据  |
| 8   | `HAS_GEOMETRY_TYPE` | 对象属性 | L1→L1 | —   | 数据  |
| 9   | `HAS_ATTRIBUTE_SCHEMA` | 对象属性 | L1→L1 | —   | 数据  |
| 10  | `SOLVES` | 对象属性 | L2→L2 | —   | 算法  |
| 11  | `HAS_INPUT_SPEC` | 对象属性 | L2→L2 | —   | 算法  |
| 12  | `HAS_OUTPUT_SPEC` | 对象属性 | L2→L2 | —   | 算法  |
| 13  | `HAS_PRECONDITION` | 对象属性 | L2→L2 | —   | 算法  |
| 14  | `HAS_POSTCONDITION` | 对象属性 | L2→L2 | —   | 算法  |
| 15  | `ALTERNATIVE_TO` | 对称属性 | L2↔L2 | weight, lastValidated | **自修复** |
| 16  | `HAS_IMPL` | 对象属性 | L2→L2 | —   | 算法  |
| 17  | `EXPECTS_DATATYPE` | 对象属性 | **L2→L1** | —   | **数据-算法** |
| 18  | `EXPECTS_GEOMETRY` | 对象属性 | **L2→L1** | —   | **数据-算法** |
| 19  | `EXPECTS_CRS` | 对象属性 | **L2→L1** | —   | **数据-算法** |
| 20  | `OUTPUTS_DATATYPE` | 对象属性 | **L2→L1** | —   | **数据-算法** |
| 21  | `FROM_FORMAT` / `TO_FORMAT` | 对象属性 | L2→L1 | —   | 数据-算法 |
| 22  | `FROM_DATATYPE` / `TO_DATATYPE` | 对象属性 | L2→L1 | —   | 数据-算法 |
| 23  | `HAS_STEP` | 对象属性 | L3→L3 | order | 工作流 |
| 24  | `USES_ALGORITHM` | 对象属性 | **L3→L2** | —   | **工作流-算法** |
| 25  | `REQUIRES_DATATYPE` | 对象属性 | **L3→L1** | —   | **工作流-数据** |
| 26  | `PREFERRED_SOURCE` | 对象属性 | **L3→L1** | priority | **工作流-数据** |
| 27  | `PRODUCES_DATATYPE` | 对象属性 | **L3→L1** | —   | **工作流-数据** |
| 28  | `DEPENDS_ON` | 对象属性 | L3→L3 | —   | 工作流 |
| 29  | `APPLIES_TO` | 对象属性 | **L3→L4** | —   | **工作流-灾害** |
| 30  | `INSTANTIATES` | 对象属性 | L3→L3 | —   | 工作流 |
| 31  | `TRIGGERS` | 对象属性 | **L4→L3** | —   | **灾害-工作流** |
| 32  | `HAS_DATA_NEED` | 对象属性 | L4→L4 | —   | 灾害  |
| 33  | `NEEDS_DATATYPE` | 对象属性 | **L4→L1** | —   | **灾害-数据** |
| 34  | `CAN_BE_SATISFIED_BY` | 对象属性 | **L4→L1** | —   | **灾害-数据** |
| 35  | `HAS_TYPE` | 对象属性 | L4→L4 | —   | 灾害  |
| 36  | `HAS_SEVERITY` | 对象属性 | L4→L4 | —   | 灾害  |
| 37  | `IN_PHASE` | 对象属性 | L4→L4 | —   | 灾害  |
| 38  | `FOR_DISASTER_TYPE` | 对象属性 | L4→L4 | —   | 灾害  |
| 39  | `FOR_RESPONSE_PHASE` | 对象属性 | L4→L4 | —   | 灾害  |
| 40  | `HAS_SPATIAL_EXTENT` | 对象属性 | L4→L4 | —   | 灾害  |
| 41  | `BROADER` | 传递对象属性 | 多层  | —   | 层级分类 |
| 42  | `USED_ALGORITHM` | 对象属性 | L3→L2 | —   | 实例追踪 |
| 43  | `USED_SOURCE` | 对象属性 | L3→L1 | —   | 实例追踪 |
| 44  | `REPAIRED_STEP` | 对象属性 | L3→L3 | —   | 自修复 |

---

## 9 对外接口：LLM RAG 检索的关键查询模板

以下 Cypher 查询模板是 GeoFusion Agent 推理规划阶段 (Stage 1: KG 骨架检索) 的核心接口：

### 9.1 按灾害类型检索工作流骨架

```cypher
// Q1: 给定灾害类型和响应阶段，检索最匹配的工作流模式
MATCH (dt:DisasterType {name: $disaster_type})
MATCH (rp:ResponsePhase {name: $response_phase})
MATCH (st:ScenarioType)-[:FOR_DISASTER_TYPE]->(dt)
MATCH (st)-[:FOR_RESPONSE_PHASE]->(rp)
MATCH (wp:WorkflowPattern)-[:APPLIES_TO]->(st)
OPTIONAL MATCH (wp)-[:HAS_STEP]->(step:StepTemplate)
WITH wp, collect(step) AS steps
ORDER BY wp.successRate DESC, wp.usageCount DESC
RETURN wp, steps
LIMIT 3
```

### 9.2 检查区域内数据可用性

```cypher
// Q2: 给定空间范围和数据主题，检索可用数据源
MATCH (ds:DataSource)-[:PROVIDES]->(dt:DataType)-[:HAS_THEME]->(th:Theme)
WHERE th.name IN $required_themes
  AND ds.isActive = true
MATCH (ds)-[:HAS_COVERAGE]->(se:SpatialExtent)
WHERE se.minLon <= $max_lon AND se.maxLon >= $min_lon
  AND se.minLat <= $max_lat AND se.maxLat >= $min_lat
OPTIONAL MATCH (ds)-[:HAS_QUALITY]->(qp:QualityProfile)
RETURN ds, dt, th, qp
ORDER BY qp.overallScore DESC
```

### 9.3 V(tᵢ) 验证查询

```cypher
// Q3: 验证步骤 (dataType, algorithm) 的兼容性
MATCH (a:Algorithm {algoId: $algo_id})-[:HAS_INPUT_SPEC]->(spec:InputSpec)
                                       -[:EXPECTS_DATATYPE]->(expected:DataType)
MATCH (actual:DataType {typeId: $data_type_id})

// 直接兼容
OPTIONAL MATCH direct WHERE actual = expected

// 经转换兼容
OPTIONAL MATCH path = shortestPath((actual)-[:CAN_TRANSFORM_TO*1..3]->(expected))

RETURN
  CASE
    WHEN actual = expected THEN {valid: true, type: 'direct', path: null}
    WHEN path IS NOT NULL THEN {valid: true, type: 'via_transform',
                                 path: [n IN nodes(path) | n.typeId]}
    ELSE {valid: false, type: 'incompatible', path: null}
  END AS validation
```

### 9.4 查找替代算法

```cypher
// Q4: 算法执行失败时，查找替代算法
MATCH (failed:Algorithm {algoId: $failed_algo_id})
      -[:ALTERNATIVE_TO]->(alt:Algorithm)
WHERE alt.isActive = true OR NOT exists(alt.isActive)
RETURN alt
ORDER BY alt.successRate DESC
LIMIT 3
```

### 9.5 查找数据转换路径

```cypher
// Q5: 数据类型不兼容时，查找最短转换路径
MATCH path = shortestPath(
    (from:DataType {typeId: $from_type})-[:CAN_TRANSFORM_TO*1..4]->(to:DataType {typeId: $to_type})
)
WITH path, reduce(cost = 0.0, r IN relationships(path) | cost + r.cost) AS totalCost
RETURN [n IN nodes(path) | n.typeId] AS typePath,
       [r IN relationships(path) | r.via] AS transformOps,
       totalCost
ORDER BY totalCost ASC
LIMIT 1
```

---

## 10 本体演进机制

### 10.1 经验学习写回规则

| 触发条件 | 写回操作 | 影响的 KG 要素 |
| --- | --- | --- |
| 工作流执行成功 | `wp.successRate` 更新 (指数移动平均) | WorkflowPattern |
| 工作流执行成功且无匹配模式 | 提取为新 WorkflowPattern | 新增 WorkflowPattern + StepTemplate |
| 替代算法修复成功 | `alternativeTo.weight` 增加 | Algorithm 关系权重 |
| 替代算法修复失败 | `alternativeTo.weight` 降低 | Algorithm 关系权重 |
| 发现新的数据转换路径 | 新增 `canTransformTo` 边 | DataType 关系 |
| 算法连续失败 N 次 | `algo.isActive = false` | Algorithm |
| 数据源不可达 | `ds.isActive = false` | DataSource |

### 10.2 版本控制策略

-   WorkflowPattern 通过 `patternVersion` 和 `derivedFrom` 实现版本链追踪
    
-   Algorithm 通过 `supersedes` 关系标记版本迭代
    
-   所有枚举类（Theme/DisasterType/Task）使用 SKOS 体系，支持在线添加新概念而不破坏已有结构
    

---

## 总结

本方案设计了一套 **33 个核心类、44 条关系类型** 的完整知识图谱本体模式层，通过四层架构实现"灾害—数据—算法"三元协同：

| 协同维度 | 关键桥接机制 | 核心关系 |
| --- | --- | --- |
| **灾害↔数据** | DataNeed 作为中介 | `hasDataNeed → needsDataType → canBeSatisfiedBy` |
| **灾害↔算法** | ScenarioType + WorkflowPattern 间接关联 | `triggers → appliesTo → hasStep → usesAlgorithm` |
| **数据↔算法** | InputSpec/OutputSpec + DataType 绑定 | `expectedDataType / outputDataType / canTransformTo` |
| **三元统一** | StepTemplate 同时持有三元引用 | `requiresDataType + usesAlgorithm + belongsToPattern.appliesTo` |
| **自修复** | alternativeTo + canTransformTo | 图遍历搜索替代路径 |
| **演进学习** | RepairRecord + 成功率更新 | 经验写回 → 权重调整 → 新模式提取 |

# 开发集标签复核建议（未改 gold）

这些是来源和通用规则之间需要人审的疑点，不是新的标准答案。六条用户指定暂定标签仍按原要求计分，独立集盲标注包不含本文件。

## 20

Point coordinates for convex hull computation.

引用：Coordinates of points to construct a convex hull from

现行标准：{"template": "product_present", "parameters": {"slot": "pial", "type": "type:Surface.Pial"}}

陈述是凸包计算的点坐标，是否为内存结构而非被试必需的 pial 文件，需按 product_present 定义核对。

## 21

Cortical thickness estimate (average) for scaling law.

引用：we only had numerical values for the total and exposed surface area, as well a average cortical thickness estimates

现行标准：{"template": "product_present", "parameters": {"slot": "thickness", "type": "type:SurfaceMetric.Thickness"}}

陈述是平均皮层厚度估计；需核对它是否确实要求 SurfaceMetric.Thickness 文件，而非派生数值。

## 33

T1/T2 structural images are processed by the three structural batch scripts.

引用：处理T1/T2结构像

现行标准：{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}

陈述描述三批处理脚本对 T1/T2 的处理，需与“方法自身处理描述按 advisory”的通用规则核对。

## 38

MATLAB with Image Processing Toolbox and $FREESURFER_HOME/matlab in the MATLAB path.

引用：MATLAB is required to use the -localGI feature. Also, you will need their Image Processing Toolbox.

现行标准：{"template": "software", "parameters": {"commands": ["matlab"]}}

原文同时提到 MATLAB 和 Image Processing Toolbox，标准只保留 matlab；需明确工具箱是否应单独表达。模型归一化成 image 也不是可用命令名，不能视为标准已被推翻。

## 40

MATLAB and its Image Processing Toolbox must be installed and accessible.

引用：MATLAB is required to use the -localGI feature. Also, you will need their Image Processing Toolbox.

现行标准：{"template": "software", "parameters": {"commands": ["matlab"]}}

原文明确要求 MATLAB 与 Image Processing Toolbox；与软件模板可覆盖 toolbox 的定义存在表达范围问题。严格键分歧仍按原标准计错。

# 结构像预处理与分析环境：部署与使用说明

服务器：`xuancheng@192.168.2.110`。目录：`/data/xuancheng/structural_env`。日期：2026-10-13。

## 本批内容

| 组件 | 版本与获取方式 | 使用入口 |
| --- | --- | --- |
| AFNI | 26.3.02，官方 Linux 分发包 | `structural-env afni <命令>` |
| Convert3D | 1.4.4，官方固定 Linux 分发包；含 `c3d_affine_tool` | `structural-env c3d <命令>` |
| SynthStrip | 固定官方源码 `cf4bccf` 构建的独立 CPU SIF；普通与 no-CSF 权重 | `structural-env synthstrip <参数>` |
| Nilearn / Nipype / PyBIDS | 0.14.1 / 1.11.0 / 0.22.0，独立 Python 环境 | `structural-env analysis <Python 参数>` |
| 数值与影像 Python 包 | NumPy 2.2.6、SciPy 1.15.3、pandas 2.3.3、Matplotlib 3.10.9、scikit-learn 1.7.2、NiBabel 5.4.2、SimpleITK 2.5.6 | 同上 |
| 猕猴模板 | NMT v2.0 对称模板，含 CHARM 与匹配 SARM；标准、0.5 mm、full-head 版本 | `templates/macaque/` |
| 狨猴模板 | MBMv3 体积分发包，含 T1/T2、掩模、组织分割、图谱 | `templates/marmoset/` |
| 人脑模板 | 从现有 FSL 6.0.7.8 镜像导出的标准模板；引用已迁移的 fsaverage | `templates/human/` |

现有 PrimateX 和 FastSurfer 镜像继续通过符号链接复用。FSL 6.0.7.8、ANTs 2.4.3、FreeSurfer 7.2.0、Workbench 2.1.0、MRtrix3 3.0.2、dcm2niix 1.0.20250505，以及原有 PyTorch/MONAI 和 PrimateX 分割模型均保留。

## 登录和启用

在 Windows PowerShell 中使用已配置的 SSH 别名：

~~~powershell
ssh xuancheng
~~~

进入服务器后：

~~~bash
source /data/xuancheng/structural_env/activate.sh

structural-env analysis --version
structural-env analysis -c 'import nilearn, nipype, bids; print(nilearn.__version__, nipype.__version__, bids.__version__)'
structural-env afni afni -ver
structural-env synthstrip --help

# 原有工具
structural-env primatex antsRegistration --version
structural-env primatex wb_command -version
~~~

`activate.sh` 只为当前 shell 增加启动器路径和模板路径变量。分析 Python 是容器内的 Python 3.10.19 加上 `runtime/python-analysis/` 中的独立 venv；不能直接用服务器宿主 Python 激活这个 venv。

## 常用操作

### 查看或转换 NIfTI

~~~bash
structural-env afni 3dinfo /data/你的输入/T1.nii.gz
structural-env c3d c3d /data/你的输入/T1.nii.gz -info

# 明确指定新的输出文件
structural-env c3d c3d /data/你的输入/T1.nii.gz -o /data/你的输出/T1_copy.nii.gz
~~~

### Python 分析脚本

~~~bash
structural-env analysis /data/你的项目/analysis.py
~~~

Nipype 在该分析环境中可以调用 PrimateX 镜像内已有的 FSL/ANTs 等程序；AFNI、C3D 和 SynthStrip 由独立 SIF 提供，跨容器流程需显式调用启动器，不能假定所有 Nipype 接口都在同一容器内直接找到对应程序。

### SynthStrip 人脑去颅骨

~~~bash
structural-env synthstrip \
  -i /data/你的输入/T1.nii.gz \
  -o /data/你的输出/T1_brain.nii.gz \
  -m /data/你的输出/T1_brainmask.nii.gz
~~~

普通和 no-CSF 模型已内置。具体可选参数以 `--help` 为准。这里部署的是固定源码 CPU 构建，Docker 仓库连接超时，因此没有将它标为官方 `freesurfer/synthstrip:1.8` 镜像，也没有伪造 OCI digest。

该上游 CLI 的 `--help`/`--version` 显示信息后返回状态码 1；不能仅据这个状态码判定安装失败。普通及 no-CSF 模型已在最终 SIF 内实际推理成功，退出码均为 0，输出影像空间与输入一致，掩模为二值且非空。

SynthStrip 用于补充人脑处理；猴脑任务继续选用已有 PrimateX 物种模型及相应模板，需在代表性数据上评估质量后再改变处理方案。

### 使用物种模板

~~~bash
source /data/xuancheng/structural_env/templates/template_paths.sh
echo "$NMT_V2_T1"
echo "$NMT_V2_MASK"
echo "$MBMV3_T1"
echo "$MBMV3_MASK"
structural-env afni 3dinfo "$NMT_V2_T1"
~~~

CHARM/SARM 的合并 NIfTI 在本包中为 `X × Y × Z × 1 × 6`。单层图谱位于 `supplemental_CHARM/` 和 `supplemental_SARM/`，不要把层级轴当成空间轴。详细路径见服务器 `templates/README_templates_20261013.md`。

## 镜像、缓存和复现

~~~text
/data/xuancheng/structural_env/
  activate.sh             当前 shell 启用入口
  bin/structural-env      统一容器启动器
  images/                 新 SIF 和已有 SIF 引用
  runtime/python-analysis Python 分析独立 venv
  templates/              人脑、猕猴、狨猴模板
  models/primx-existing   原有 PrimateX 模型引用
  recipes/                构建脚本、依赖锁及离线重建脚本
  manifests/              版本、来源、校验值和验收记录
  licenses/               软件与模型许可记录
  cache/                  原始包、wheelhouse、构建缓存
  tests/                  合成输入和功能验证
  logs/                   安装、构建、推理日志
~~~

Python 完整版本锁为 `recipes/python-analysis.lock.txt`，离线 wheelhouse 为 `cache/python-wheels/`。`recipes/restore-python-offline.sh` 可在相同路径、相同基础镜像下新建 `runtime/python-analysis-restored/`；脚本拒绝覆盖已有目录。

现有镜像与 fsaverage/PrimateX 模型使用绝对路径引用。若迁移环境，要同时保存引用的原文件，或调整路径后重建和重新验收。实际使用的 SIF 与下载包 SHA256 已保存在 `manifests/`；本地生成的哈希表示本次文件身份，不等于发布者签名认证。

启动器默认将 OpenMP/ITK/OpenBLAS 线程数设为 8，可在运行前修改：

~~~bash
export STRUCTURAL_THREADS=4
~~~

## 验收范围

详细结果以 `manifests/` 中实际生成的验收记录为准。Python 已通过依赖检查、包导入、合成 NIfTI 读写、Nilearn 平滑/重采样、SimpleITK 读取、PyBIDS 索引，以及 Nipype 调用 FSL 并比对数值结果。猴脑模板已通过 128/128 个实际 NIfTI 全量读取及有限体素检查、13/13 对空间几何一致性检查；人脑 MNI152 2 mm 模板与掩模也已检查。

AFNI/Convert3D 通过 20 项检查，包含 `@animal_warper` 帮助、`3dAllineate` 身份变换、`3dQwarp` 合成影像、C3D 图像运算与仿射工具；`@chauffeur_afni` 成功生成三方向 QC PNG。统一启动器的 AFNI/C3D 影像运算另与 Python 结果及空间信息比对通过，SynthStrip 的两个模型实际推理通过。

总清单位于服务器 `manifests/environment-20261013.json`。新 SIF 的 SHA256 为：

~~~text
980016ba9f8c92189bd3d5fd15474c708ffd87add86cc1d1037b9bb160a2b36d  afni-c3d.sif
0a0aefcf9165b47b96b84765019d87cee548f3bb03f5c10d7baee2000c9069f6  synthstrip-cpu-source-cf4bccf.sif
~~~

容器功能验证使用新的测试目录，不对已有被试执行完整重建，也不表示已经评估每个物种的处理精度。新增软件没有自动接入 PrimateX Agent 的工具注册。

AFNI 本批主要提供结构像处理与 QC 所需环境；需要 R 的统计模块未配置 `libR`/R 运行环境。使用相应统计命令前需另行补充。

FreeSurfer 运行许可证只在运行时只读绑定；没有写入新镜像。原有 API 配置、服务器系统库、GPU 驱动和正在运行的服务没有修改。模板包内文档与引用信息已保留；MBMv3 分发包没有独立许可文件，未将 AFNI 软件许可套用到图谱。

## 官方来源

- [AFNI 容器与安装说明](https://afni.nimh.nih.gov/pub/dist/doc/htmldoc/background_install/container.html)
- [Convert3D 官方仓库](https://github.com/pyushkevich/c3d)
- [SynthStrip 官方软件与模型](https://surfer.nmr.mgh.harvard.edu/docs/synthstrip/)
- [Nilearn](https://nilearn.github.io/stable/index.html)、[Nipype](https://nipype.readthedocs.io/en/latest/)、[PyBIDS](https://bids-standard.github.io/pybids/)
- [NMT v2 / CHARM](https://afni.nimh.nih.gov/pub/dist/doc/htmldoc/nonhuman/macaque_tempatl/template_nmtv2.html)、[SARM](https://afni.nimh.nih.gov/pub/dist/doc/htmldoc/nonhuman/macaque_tempatl/atlas_sarm.html)
- [MBM 图谱项目](https://marmosetbrainmapping.gitlab.io/atlas.html)
- [Apptainer 文档](https://apptainer.org/docs/user/1.4/)

SynthSeg、sMRIPrep、MRIQC、SPM/CAT，以及新版 FSL/ANTs/FreeSurfer 等属于之前列出的可选第二批，本次未下载。

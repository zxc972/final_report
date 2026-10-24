# 第二十三轮：算法2补实验

fsaverage先运行，随后20名已登记IXI开发被试；左右半球共126个条件记录，C1/C2/C3各42，跳过0。82个mris_ca_label任务全部成功（fsaverage DKT2个，IXI20的DK/Destrieux共80个）；DKT在IXI使用已有mapped.annot。模型调用0。原始输入文件前后指纹无变化，输出只在临时目录。

先核对容器recon-all7.2脚本，再选其默认GCS（左右半球各一份）：

- DK：`{lh,rh}.DKaparc.atlas.acfb40.noaparc.i12.2016-08-02.gcs`。
- Destrieux：`{lh,rh}.CDaparc.atlas.acfb40.noaparc.i12.2016-08-02.gcs`。
- DKT：`{lh,rh}.DKTaparc.atlas.acfb40.noaparc.i12.2016-08-02.gcs`。

分类器目录为$FREESURFER_HOME/average；没有采用仅在-dkt2020选项下使用的2020分类器。固定seed1234，使用既有cortex.label；IXI均使用对应aseg.presurf.mgz，fsaverage没有该卷时不加该参数，逐任务回执已记录。最初一次预检因未绑定现有运行时license失败，未产生annot；随后只补现有license的只读挂载，参数未因结果调整。

θ=.5、κ=.8、π=.8、τ=.2，关键词表不变。临时subjects的surf/mri链接到只读输入；label内为原标签链接和临时生成文件。

## C1/C2准确率

每个被试左右半球按标签数合并后，计算20人的中位数/最小值。错误数为全部半球标签累计。

| 条件 | 方法 | fsaverage | IXI20中位数 | IXI20最小值 | fsaverage错误 | IXI20错误 |
|---|---|---:|---:|---:|---:|---:|
| C1_DK_to_DKT | overlap_weighted | 100.00% | 100.00% | 98.39% | 0 | 3 |
| C1_DK_to_DKT | overlap_unweighted | 100.00% | 100.00% | 98.39% | 0 | 2 |
| C1_DK_to_DKT | name_exact | 100.00% | 100.00% | 100.00% | 0 | 0 |
| C1_DK_to_DKT | keyword | 93.55% | 93.55% | 93.55% | 4 | 80 |
| C2_DKT_to_DK | overlap_weighted | 100.00% | 100.00% | 100.00% | 0 | 0 |
| C2_DKT_to_DK | overlap_unweighted | 100.00% | 100.00% | 100.00% | 0 | 0 |
| C2_DKT_to_DK | name_exact | 91.18% | 91.18% | 91.18% | 6 | 120 |
| C2_DKT_to_DK | keyword | 94.12% | 94.12% | 94.12% | 4 | 80 |

错误标签：加权C1为IXI095右rostralanteriorcingulate、IXI288左及IXI303左caudalanteriorcingulate，均预测frontal而参考为cingulate；非加权仅前两例。C2重叠方法无错误。name_exact在C2无法覆盖bankssts、frontalpole、temporalpole；keyword在C1/C2均漏precuneus与parstriangularis，模板与每名开发被试一致。逐条错误另列JSON/CSV。

## C3 Dice分布

C3无精确标签金标准，报告相对DK粗分区的几何重叠。单位为每半球×6粗区域：fsaverage12个观察，IXI20共240个观察；不是标签准确率。

| 方法 | 数据 | n | 最小 | Q25 | 中位数 | Q75 | 最大 | 均值 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| keyword | IXI20 | 240 | 0.464962 | 0.589059 | 0.659507 | 0.813622 | 0.912007 | 0.690952 |
| keyword | fsaverage | 12 | 0.509741 | 0.580081 | 0.623985 | 0.786375 | 0.892983 | 0.674448 |
| name_exact | IXI20 | 240 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| name_exact | fsaverage | 12 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| overlap_unweighted | IXI20 | 240 | 0.477541 | 0.688833 | 0.852567 | 0.902526 | 0.941024 | 0.808204 |
| overlap_unweighted | fsaverage | 12 | 0.633023 | 0.709181 | 0.848880 | 0.903954 | 0.922339 | 0.812533 |
| overlap_weighted | IXI20 | 240 | 0.477541 | 0.694875 | 0.852180 | 0.902526 | 0.941024 | 0.809933 |
| overlap_weighted | fsaverage | 12 | 0.633023 | 0.709181 | 0.850964 | 0.903954 | 0.922339 | 0.813008 |

## 相对fsaverage映射一致率

原脚本比较加权方法的“标签→粗区域”映射。主表每名被试先平均左右半球，再报20人的分布；另列40个半球记录的最低值。

| 条件 | 被试中位数 | 被试最小值 | 半球最小值 |
|---|---:|---:|---:|
| C1_DK_to_DKT | 100.00% | 98.39% | 96.77% |
| C2_DKT_to_DK | 100.00% | 100.00% | 100.00% |
| C3_DK_to_Destrieux | 97.30% | 95.95% | 93.24% |

## θ敏感性（仅分析，不选择新默认值）

| 条件 | 数据 | θ | 准确率均值 | 半球平均Dice再均值 | 未分配标签总数 | resolved粗区域数 |
|---|---|---:|---:|---:|---:|---:|
| C1_DK_to_DKT | IXI20 | 0.3 | 99.76% | 0.935475 | 0 | 199 |
| C1_DK_to_DKT | IXI20 | 0.4 | 99.76% | 0.935475 | 0 | 199 |
| C1_DK_to_DKT | IXI20 | 0.5 | 99.76% | 0.935475 | 0 | 199 |
| C1_DK_to_DKT | IXI20 | 0.6 | 99.19% | 0.934212 | 10 | 187 |
| C1_DK_to_DKT | IXI20 | 0.7 | 96.77% | 0.924330 | 40 | 161 |
| C1_DK_to_DKT | IXI20 | 0.8 | 92.74% | 0.910277 | 90 | 74 |
| C1_DK_to_DKT | fsaverage | 0.3 | 100.00% | 0.952224 | 0 | 12 |
| C1_DK_to_DKT | fsaverage | 0.4 | 100.00% | 0.952224 | 0 | 12 |
| C1_DK_to_DKT | fsaverage | 0.5 | 100.00% | 0.952224 | 0 | 12 |
| C1_DK_to_DKT | fsaverage | 0.6 | 100.00% | 0.952224 | 0 | 12 |
| C1_DK_to_DKT | fsaverage | 0.7 | 98.39% | 0.948201 | 1 | 10 |
| C1_DK_to_DKT | fsaverage | 0.8 | 95.16% | 0.938175 | 3 | 6 |
| C2_DKT_to_DK | IXI20 | 0.3 | 100.00% | 0.935696 | 0 | 198 |
| C2_DKT_to_DK | IXI20 | 0.4 | 100.00% | 0.935696 | 0 | 198 |
| C2_DKT_to_DK | IXI20 | 0.5 | 100.00% | 0.935696 | 0 | 198 |
| C2_DKT_to_DK | IXI20 | 0.6 | 100.00% | 0.935696 | 0 | 198 |
| C2_DKT_to_DK | IXI20 | 0.7 | 99.41% | 0.909902 | 8 | 193 |
| C2_DKT_to_DK | IXI20 | 0.8 | 98.01% | 0.844162 | 27 | 193 |
| C2_DKT_to_DK | fsaverage | 0.3 | 100.00% | 0.952224 | 0 | 12 |
| C2_DKT_to_DK | fsaverage | 0.4 | 100.00% | 0.952224 | 0 | 12 |
| C2_DKT_to_DK | fsaverage | 0.5 | 100.00% | 0.952224 | 0 | 12 |
| C2_DKT_to_DK | fsaverage | 0.6 | 100.00% | 0.952224 | 0 | 12 |
| C2_DKT_to_DK | fsaverage | 0.7 | 100.00% | 0.952224 | 0 | 12 |
| C2_DKT_to_DK | fsaverage | 0.8 | 100.00% | 0.952224 | 0 | 12 |
| C3_DK_to_Destrieux | IXI20 | 0.3 | 无精确标准 | 0.814014 | 0 | 142 |
| C3_DK_to_Destrieux | IXI20 | 0.4 | 无精确标准 | 0.814087 | 13 | 119 |
| C3_DK_to_Destrieux | IXI20 | 0.5 | 无精确标准 | 0.809933 | 86 | 50 |
| C3_DK_to_Destrieux | IXI20 | 0.6 | 无精确标准 | 0.770691 | 369 | 6 |
| C3_DK_to_Destrieux | IXI20 | 0.7 | 无精确标准 | 0.755801 | 531 | 0 |
| C3_DK_to_Destrieux | IXI20 | 0.8 | 无精确标准 | 0.730130 | 797 | 0 |
| C3_DK_to_Destrieux | fsaverage | 0.3 | 无精确标准 | 0.812911 | 0 | 6 |
| C3_DK_to_Destrieux | fsaverage | 0.4 | 无精确标准 | 0.813091 | 1 | 5 |
| C3_DK_to_Destrieux | fsaverage | 0.5 | 无精确标准 | 0.813008 | 2 | 4 |
| C3_DK_to_Destrieux | fsaverage | 0.6 | 无精确标准 | 0.773789 | 19 | 0 |
| C3_DK_to_Destrieux | fsaverage | 0.7 | 无精确标准 | 0.753177 | 27 | 0 |
| C3_DK_to_Destrieux | fsaverage | 0.8 | 无精确标准 | 0.717632 | 43 | 0 |

完整逐被试/半球指标、所有映射与错误、GCS文件SHA、命令回执、输入指纹与参数位于 `region_resolution_v2/`（仓库 `evaluation/region_resolution_v2/`）；原始annot与MRI没有加入公开Git。生成worker为仓库 `agent/experiments/round23/generate_region_annotations.py`；原实验运行器与解析算法未变。

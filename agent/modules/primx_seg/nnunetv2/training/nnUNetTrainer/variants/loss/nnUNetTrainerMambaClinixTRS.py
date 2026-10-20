
import torch
from nnunetv2.training.loss.deep_supervision import DeepSupervisionWrapper
from nnunetv2.training.nnUNetTrainer.nnUNetTrainerMambaClinix import nnUNetTrainerMambaClinix
from nnunetv2.training.loss.mambaclinix_loss import MambaClinix_compound_losses
from nnunetv2.training.loss.dice import MemoryEfficientSoftDiceLoss
import numpy as np
from nnunetv2.nets.MoR_3d import MoRLayer3D

class nnUNetTrainerMambaClinixTRS(nnUNetTrainerMambaClinix):
    def _build_loss(self):
        assert not self.label_manager.has_regions, "regions not supported by this trainer"

        # 原始 seg loss（如 Dice + CE + TopoCE）
        base_loss = MambaClinix_compound_losses(
            {'batch_dice': self.configuration_manager.batch_dice, 'smooth': 1e-5,
             'do_bg': False, 'ddp': self.is_ddp},
            {},
            {'batch_dice': self.configuration_manager.batch_dice, 'smooth': 1e-5,
             'do_bg': False, 'alpha': 0.3, 'beta': 0.4,
             'num_region_per_axis': (8, 8, 14)},
            weight_ce=1, weight_dice=1,
            ignore_label=self.label_manager.ignore_label,
            dice_class=MemoryEfficientSoftDiceLoss
        )

        # === 封装 MoR KL + Entropy loss 添加 ===
        def loss_with_mor_regularization(output, target):
            seg_loss = base_loss(output, target)

            kl_losses = []
            entropy_losses = []
            for module in self.network.modules():
                if isinstance(module, MoRLayer3D):
                    if module.kl_loss is not None:
                        kl_losses.append(module.kl_loss * getattr(module, 'kl_weight', 0.01))
                    if module.entropy_loss is not None:
                        entropy_losses.append(module.entropy_loss * getattr(module, 'entropy_weight', 0.001))
            #kl_weight = 0.01
            #entropy_weight = 0.001

            mor_reg = sum(kl_losses) + sum(entropy_losses)
            total_loss = seg_loss + mor_reg

            '''
            # ✅ 打印一次调试信息
            if self.local_rank == 0:  # only print from main process
                print(f"[Loss Breakdown] seg: {seg_loss.item():.4f}, kl: {sum(kl_losses).item():.6f}, "
                      f"entropy: {sum(entropy_losses).item():.6f}, total: {total_loss.item():.4f}")
            '''
            return total_loss

        # === 是否启用 Deep Supervision ===
        if self.enable_deep_supervision:
            deep_supervision_scales = self._get_deep_supervision_scales()
            weights = np.array([1 / (2**i) for i in range(len(deep_supervision_scales))])
            weights[-1] = 0
            weights = weights / weights.sum()

            # 注意：这里封装的是我们修改后的 loss
            loss = DeepSupervisionWrapper(loss_with_mor_regularization, weights)
        else:
            loss = loss_with_mor_regularization

        return loss


class nnUNetTrainerMambaClinixTRS_500epochs(nnUNetTrainerMambaClinixTRS):
    def __init__(
        self,
        plans: dict,
        configuration: str,
        fold: int,
        dataset_json: dict,
        unpack_dataset: bool = True,
        device: torch.device = torch.device("cuda"),
    ):
        """used for debugging plans etc"""
        super().__init__(plans, configuration, fold, dataset_json, unpack_dataset, device)
        self.num_epochs = 500

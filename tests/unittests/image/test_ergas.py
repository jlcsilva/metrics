# Copyright The Lightning team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from collections import namedtuple
from functools import partial
from typing import Union

import pytest
import torch
from torch import Tensor

from torchmetrics.functional.image.ergas import error_relative_global_dimensionless_synthesis
from torchmetrics.image.ergas import ErrorRelativeGlobalDimensionlessSynthesis
from unittests.helpers import seed_all
from unittests.helpers.testers import BATCH_SIZE, NUM_BATCHES, MetricTester

seed_all(42)

Input = namedtuple("Input", ["preds", "target", "ratio"])

_inputs = []
for size, channel, coef, ratio, dtype in [
    (12, 1, 0.9, 1, torch.float),
    (13, 3, 0.8, 2, torch.float32),
    (14, 1, 0.7, 3, torch.double),
    (15, 3, 0.5, 4, torch.float64),
]:
    preds = torch.rand(NUM_BATCHES, BATCH_SIZE, channel, size, size, dtype=dtype)
    _inputs.append(Input(preds=preds, target=preds * coef, ratio=ratio))


def _baseline_ergas(
    preds: Tensor,
    target: Tensor,
    ratio: Union[int, float] = 4,
    reduction: str = "elementwise_mean",
) -> Tensor:
    """Reference implementation of Erreur Relative Globale Adimensionnelle de Synthèse."""
    reduction_options = ("elementwise_mean", "sum", "none")
    if reduction not in reduction_options:
        raise ValueError(f"reduction has to be one of {reduction_options}, got: {reduction}.")
    # reshape to (batch_size, channel, height*width)
    b, c, h, w = preds.shape
    sk_preds = preds.reshape(b, c, h * w)
    sk_target = target.reshape(b, c, h * w)
    # compute rmse per band
    diff = sk_preds - sk_target
    sum_squared_error = torch.sum(diff * diff, dim=2)
    rmse_per_band = torch.sqrt(sum_squared_error / (h * w))
    mean_target = torch.mean(sk_target, dim=2)
    # compute ergas score
    ergas_score = 100 * ratio * torch.sqrt(torch.sum((rmse_per_band / mean_target) ** 2, dim=1) / c)
    # reduction
    if reduction == "sum":
        to_return = torch.sum(ergas_score)
    elif reduction == "elementwise_mean":
        to_return = torch.mean(ergas_score)
    else:
        to_return = ergas_score
    return to_return


@pytest.mark.parametrize("reduction", ["sum", "elementwise_mean"])
@pytest.mark.parametrize(
    "preds, target, ratio",
    [(i.preds, i.target, i.ratio) for i in _inputs],
)
class TestErrorRelativeGlobalDimensionlessSynthesis(MetricTester):
    @pytest.mark.parametrize("ddp", [True, False])
    def test_ergas(self, reduction, preds, target, ratio, ddp):
        self.run_class_metric_test(
            ddp,
            preds,
            target,
            ErrorRelativeGlobalDimensionlessSynthesis,
            partial(_baseline_ergas, ratio=ratio, reduction=reduction),
            metric_args={"ratio": ratio, "reduction": reduction},
        )

    def test_ergas_functional(self, reduction, preds, target, ratio):
        self.run_functional_metric_test(
            preds,
            target,
            error_relative_global_dimensionless_synthesis,
            partial(_baseline_ergas, ratio=ratio, reduction=reduction),
            metric_args={"ratio": ratio, "reduction": reduction},
        )

    # ERGAS half + cpu does not work due to missing support in torch.log
    @pytest.mark.xfail(reason="ERGAS metric does not support cpu + half precision")
    def test_ergas_half_cpu(self, reduction, preds, target, ratio):
        self.run_precision_test_cpu(
            preds,
            target,
            ErrorRelativeGlobalDimensionlessSynthesis,
            error_relative_global_dimensionless_synthesis,
        )

    @pytest.mark.skipif(not torch.cuda.is_available(), reason="test requires cuda")
    def test_ergas_half_gpu(self, reduction, preds, target, ratio):
        self.run_precision_test_gpu(
            preds, target, ErrorRelativeGlobalDimensionlessSynthesis, error_relative_global_dimensionless_synthesis
        )


def test_error_on_different_shape(metric_class=ErrorRelativeGlobalDimensionlessSynthesis):
    metric = metric_class()
    with pytest.raises(RuntimeError):  # todo
        metric(torch.randn([1, 3, 16, 16]), torch.randn([1, 1, 16, 16]))


def test_error_on_invalid_shape(metric_class=ErrorRelativeGlobalDimensionlessSynthesis):
    metric = metric_class()
    with pytest.raises(ValueError):  # noqa: PT011  # todo
        metric(torch.randn([3, 16, 16]), torch.randn([3, 16, 16]))


def test_error_on_invalid_type(metric_class=ErrorRelativeGlobalDimensionlessSynthesis):
    metric = metric_class()
    with pytest.raises(TypeError):  # todo
        metric(torch.randn([3, 16, 16]), torch.randn([3, 16, 16], dtype=torch.float64))
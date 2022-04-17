import logging

import torch
import torch.distributions as D
from torch import nn
from torch.nn import functional as F

LOGGER = logging.getLogger(__name__)


class GMM(nn.Module):
    """Base class for Gaussian Mixture Models (GMM).
    Args:
        k (int): The number of mixture components.
        data (torch.Tensor): Data to initialize means from. Must provide more data points than clusters!
        loc (torch.Tensor): The means of the Gaussian distributions.
        cov (torch.Tensor): The covariance matrices of the Gaussian distributions.
        covariance_type (str): Which covariance type to learn? Options: {full, diag}. Default: full.
    """

    def __init__(
        self,
        k: int,
        data: torch.Tensor,
        covariance_type: str = "full",
        **kwargs,
    ) -> None:
        """Initialize the GMM model.
        Args:
            See class description.
        """
        super().__init__()
        self.k = k
        self.covariance_type = covariance_type

        self._mix: D.distribution = None
        self._comp: D.distribution = None

        self._eps = torch.finfo(torch.float32).eps
        self._fitted = False
        self._initalize(data)

    def forward(self, X):
        """Compute the weighted log probabilities for each sample.
        Args:
            X (torch.Tensor): Data matrix (n_samples, n_features).
        Returns:
            log_prob (torch.Tensor): Log probabilities of each data point in X. (n_sample, )
        """
        if not self._fitted:
            raise Exception()

        weighted_log_prob = self._comp.log_prob(X.unsqueeze(1)) + torch.log_softmax(
            self._mix.logits, dim=-1
        )
        return torch.logsumexp(weighted_log_prob, dim=1, keepdim=True)

    def load_state_dict(self, *args, **kwargs):
        super().load_state_dict(*args, **kwargs)

        # only loc and cov are stored in the state dict, thus we have to build distributions afterwards
        self._build_distributions()
        self._fitted = True

    def to(self, *args, **kwargs):
        self = super().to(*args, **kwargs)
        self._build_distributions()
        return self

    def cuda(self, *args, **kwargs):
        self = super().cuda(*args, **kwargs)
        self._build_distributions()
        return self

    def cpu(self, *args, **kwargs):
        self = super().cpu(*args, **kwargs)
        self._build_distributions()
        return self

    def _build_distributions(self):
        raise NotImplementedError(
            "_build_distributions must be implemented by subclass!"
        )

    def _build_distributions(self):
        # create mutlivariate gaussian
        if self.covariance_type == "full":
            cov = self.cov
            self._comp = D.MultivariateNormal(self.loc, cov)
        elif self.covariance_type == "diag":
            # since we keep diagonal in log space
            cov = torch.stack([torch.diag(torch.exp(c)) for c in self.cov])

            # we use tril matrix
            self._comp = D.MultivariateNormal(self.loc, scale_tril=cov)
        else:
            raise Exception()

        # create mixing weights
        self._mix = D.Categorical(F.softmax(self.pi, dim=0))

    def _initalize(self, data: torch.Tensor):
        # equal prior distribution
        d = data.size(1)
        pi = torch.full(
            fill_value=(1.0 / self.k),
            size=[
                self.k,
            ],
        )

        # draw from Gaussian distribution
        loc = torch.randn(self.k, d)
        prob = torch.ones(len(data)) / len(data)
        loc = data[torch.multinomial(prob, num_samples=self.k)]

        # simple covariance matrix
        if self.covariance_type == "full":
            cov = torch.stack([torch.eye(d) for _ in range(self.k)])
        elif self.covariance_type == "diag":
            cov = torch.stack([torch.ones(d) for _ in range(self.k)])

        self._initalize_parameters(pi, loc, cov)
        self._build_distributions()

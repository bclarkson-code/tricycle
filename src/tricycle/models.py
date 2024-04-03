import cupy as cp

from tricycle.blocks import GPT2TransformerBlock
from tricycle.configs import GPTConfig
from tricycle.layers import Dense, Dropout, Layer
from tricycle.optimisers import Optimiser
from tricycle.tensor import Tensor, to_tensor


class GPT(Layer):
    def __init__(self, config: GPTConfig):
        self.embedding_dim = config.embedding_dim
        self.context_window = config.context_window
        self.token_embedding = Dense(
            to_size=self.embedding_dim, from_size=config.vocab_size
        )
        self.position_embedding = Dense(
            to_size=self.embedding_dim, from_size=self.context_window
        )
        self.input_dropout = Dropout(config.input_dropout_prob)

        self.blocks = [
            GPT2TransformerBlock(
                embedding_dim=self.embedding_dim,
                n_heads=config.n_heads,
                context_window=self.context_window,
                expansion_ratio=config.expansion_ratio,
                activation_fn=config.activation_fn,
                attention_dropout_prob=config.attention_dropout_prob,
            )
            for _ in range(config.n_layers)
        ]

        self.head = Dense(
            to_size=config.vocab_size, from_size=self.embedding_dim
        )

    def forward(self, x: Tensor):
        """
        Forward pass of the transformer. inputs is expected to be a one-hot
        encoded tensor
        """
        xp = cp.get_array_module(x._data)
        _, n_tokens, _ = x.shape
        assert n_tokens <= self.context_window, (
            "Can't have more tokens than context window. ",
            f"Found {n_tokens=} and {self.context_window=}",
        )

        position = to_tensor(xp.arange(n_tokens))

        pos_embedding = (
            self.position_embedding(position).repeat(n_tokens).e("ET->TE")
        )
        token_embedding = self.token_embedding(x)

        embedding = token_embedding + pos_embedding
        embedding = self.input_dropout(embedding)

        for block in self.blocks:
            embedding = block(embedding)

        return self.head(embedding)

    def zero_grad(self):
        self.token_embedding.zero_grad()
        self.position_embedding.zero_grad()
        self.head.zero_grad()
        for block in self.blocks:
            block.zero_grad()

    def update(self, optimiser: Optimiser):
        self.token_embedding.update(optimiser)
        self.position_embedding.update(optimiser)
        self.head.update(optimiser)
        for block in self.blocks:
            block.update(optimiser)

    def to_gpu(self):
        self.token_embedding.to_gpu()
        self.position_embedding.to_gpu()
        self.head.to_gpu()
        for block in self.blocks:
            block.to_gpu()

    def from_gpu(self):
        self.token_embedding.from_gpu()
        self.position_embedding.from_gpu()
        self.head.from_gpu()
        for block in self.blocks:
            block.from_gpu()

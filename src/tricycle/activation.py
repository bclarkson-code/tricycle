from numpy.typing import ArrayLike

from tricycle.functions import sigmoid
from tricycle.initialisers import init_xavier
from tricycle.layers import Dense, Layer
from tricycle.optimisers import Optimiser
from tricycle.tensor import Tensor, to_tensor
from tricycle.unary import UnaryMax


class ReLU(Layer):
    def forward(self, x: Tensor):
        return UnaryMax()(x, 0)


class Swish(Layer):
    """
    A Swish activation function. Note, because we have omitted the bias, this
    is equivalent to the Silu activation function
    """

    def forward(self, x: Tensor):
        return x * sigmoid(x)


class GeLU(Layer):
    """
    A GeLU activation function.

    Because the 100% accurate version uses erf, which involves an integral,
    we provide a fast approximation of the function
    """

    CONST_1 = 0.7978845608028654
    CONST_2 = 0.044715

    def __init__(self, *args, approximate: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.approximate = approximate

    def backward(self, grad: Tensor):
        xp = grad.xp

        inner = (
            self.CONST_1 * self._input * (1 + self.CONST_2 * self._input**2)
        )
        coef = (
            self.CONST_1
            * self._input
            * (1 + self.CONST_2 * 3 * self._input**2)
        )

        left = xp.tanh(inner)
        cosh = xp.cosh(inner)
        right = coef / (cosh * cosh)
        self._grad = 0.5 * (1 + left + right) * grad.array

        result = to_tensor(
            self._grad,
            is_batched=grad.is_batched,
            requires_grad=grad.requires_grad,
        )
        result.name = "gelu_back"
        return result

    def forward(self, tensor: Tensor):
        xp = tensor.xp
        self._input = tensor.array
        inner = self.CONST_1 * (tensor.array + self.CONST_2 * tensor.array**3)
        result = tensor.array * 0.5 * (1 + xp.tanh(inner))

        result = to_tensor(
            result,
            is_batched=tensor.is_batched,
            requires_grad=tensor.requires_grad,
        )
        result.name = "gelu"
        result.args = (tensor,)
        result.back_fns = (self.backward,)
        return result


class GLU(Layer):
    """
    A gated linear unit
    """

    linear: Dense

    def __init__(self, size: int, initialiser=init_xavier, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.linear = Dense(size, 2 * size, initialiser)
        self.layers = [self.linear]

    def forward(self, x: Tensor):
        x = self.linear(x)
        left, right = x.split(2)
        return left * sigmoid(right)

    def update(self, optimiser: Optimiser):
        self.linear.update(optimiser)

    def zero_grad(self):
        self.linear.zero_grad()

    def to_gpu(self):
        self.linear.to_gpu()

    def from_gpu(self):
        self.linear.from_gpu()


class SwiGLU(Layer):
    """
    A SwiGLU layer. This is a modification to a GLU where we replace
    the sigmoid with a swish
    """

    linear: Dense
    bias: Tensor

    def __init__(
        self,
        from_size: int,
        to_size: int,
        initialiser=init_xavier,
        tunable_bias=True,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.bias = to_tensor(1.0, requires_grad=tunable_bias, name="bias")
        self.tunable_bias = tunable_bias
        self.weights = initialiser((from_size, 2 * to_size))
        self.tensors = {"weights": self.weights}

    def _sigmoid(self, x, xp) -> ArrayLike:
        return 1 / (1 + xp.exp(x))

    def forward(self, tensor: Tensor):
        match tensor.ndim:
            case 1:
                subscript = "a,aW->W"
                self.weight_subscript = "a,W->aW"
                self.grad_subscript = "aW,W->a"
            case 2:
                subscript = "Tb,bW->TW"
                self.weight_subscript = "Tb,TW->bW"
                self.grad_subscript = "bW,TW->Tb"
            case 3:
                subscript = "zTb,bW->zTW"
                self.weight_subscript = "zTb,zTW->bW"
                self.grad_subscript = "bW,zTW->zTb"
            case 4:
                subscript = "zxTb,bW->zxTW"
                self.weight_subscript = "zxTb,zxTW->bW"
                self.grad_subscript = "bW,zxTW->zxTb"
            case _:
                raise NotImplementedError(
                    f"Cannot pass tensor with shape {tensor.shape} "
                    f"and {tensor.is_batched=}"
                    "through a Dense layer"
                )

        xp = tensor.xp
        x = tensor.array

        breakpoint()
        projected = xp.einsum(subscript, x, self.weights.array)
        left = projected[..., : self.size]
        right = projected[..., self.size :]

        self.sigmoid_out = self._sigmoid(right, xp)

        result = left * self.sigmoid_out
        return Tensor(
            result,
            args=(tensor, self.weights),
            back_fns=(self.backwards, self.back_weights),
            is_batched=tensor.is_batched,
        )

    def backwards(self, grad: Tensor) -> Tensor:
        xp = grad.xp
        sigmoid_grad = self.sigmoid_output * (1 - self.sigmoid_output)
        out = grad.array * (
            self.sigmoid_out
            + self._input
            * xp.einsum(self.grad_subscript, sigmoid_grad, self.weights)
        )
        return Tensor(out, name="back_swiglu", is_batched=grad.is_batched)

    def back_weights(self, grad: Tensor) -> Tensor:
        xp = grad.xp
        sigmoid_grad = self.sigmoid_output * (1 - self.sigmoid_output)
        left = grad.array * self._input * sigmoid_grad
        right = self._input
        weight_grad = xp.einsum(self.weight_subscript, left, right)

        return Tensor(
            weight_grad, name="back_swiglu_weights", is_batched=grad.is_batched
        )

    def update(self, optimiser: Optimiser):
        self.linear.update(optimiser)
        self.bias = optimiser(self.bias)

    def zero_grad(self):
        self.linear.zero_grad()

    def to_gpu(self):
        self.linear.to_gpu()

    def from_gpu(self):
        self.linear.from_gpu()

import numpy as np
from matplotlib import pyplot as plt

from tricycle_v2.loss import mean_squared_error
from tricycle_v2.ops import repeat
from tricycle_v2.reduce import radd
from tricycle_v2.tensor import to_tensor


def test_can_mean_square_error():
    y_true = to_tensor([[0, 0, 1], [0, 1, 0], [1 / 3, 1 / 3, 1 / 3]])
    y_pred = to_tensor([[0, 0, 1], [0, 0, 1], [0, 0, 1]])

    mse = mean_squared_error(y_true, y_pred)

    assert mse.shape == (3,)
    assert np.allclose(mse, np.array([0, 2 / 3, 2 / 9]))


def test_can_linear_regression():
    np.random.seed(42)

    n = 10
    learning_rate = 1e-2
    x = np.linspace(-10, 10, n)
    y = x * 2 + 1 + np.random.normal(loc=0, scale=0.01, size=n)

    x = to_tensor(x.reshape(-1, 1), requires_grad=False, name="x")
    y = to_tensor(y.reshape(-1, 1), requires_grad=False, name="y")

    slope = to_tensor([0.01], name="slope")
    intercept = to_tensor([0.01], name="intercept")

    losses = []
    for _ in range(100):
        repeated_slope = repeat("j->ij", slope, x.shape)
        repeated_intercept = repeat("j->ij", intercept, x.shape)

        y_pred = x * repeated_slope + repeated_intercept
        mse = mean_squared_error(y, y_pred)
        loss = radd(mse, "i->") / y.shape[0]

        losses.append(loss)

        loss.backward()

        slope = to_tensor(slope - slope.grad * learning_rate, name="slope")
        intercept = to_tensor(
            intercept - intercept.grad * learning_rate, name="intercept"
        )

    _, ax = plt.subplots()
    ax.plot(losses)
    ax.set_yscale("log")
    plt.show()

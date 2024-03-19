import logging
from copy import copy

import numpy as np
import pytest
from matplotlib import pyplot as plt
from sklearn.datasets import load_diabetes, load_iris, load_linnerud
from sklearn.preprocessing import RobustScaler

from tricycle.einsum import Einsum
from tricycle.initialisers import init_xavier
from tricycle.loss import cross_entropy, mean_square_error
from tricycle.tensor import to_tensor, unvectorise, vectorise
from tricycle.utils import r_squared, smooth

logger = logging.getLogger(__name__)

slow_test = pytest.mark.skipif(
    "not config.getoption('--run-slow')",
    reason="Only run when --run-slow is given",
)


def test_can_mean_square_error():
    y_true = to_tensor([0, 0, 1])
    y_pred = to_tensor([0, 0.5, 0.5])

    mse = mean_square_error(y_true, y_pred)

    assert mse.close_to(1 / 6)


def test_can_cross_entropy():
    y_true = to_tensor([0, 0, 1])
    y_pred = to_tensor([0, 0, 0])

    loss = cross_entropy(y_true, y_pred)

    assert loss.close_to(1.0986122886681098)


def test_can_single_linear_regression_step():
    """
    A single step of linear regression
    """
    x_input = [1]
    y_input = [3]
    slope = to_tensor([0.02])
    intercept = to_tensor([0.01])

    x_input = to_tensor(x_input, requires_grad=False, name="x")
    y_input = to_tensor(y_input, requires_grad=False, name="y")

    y_pred = x_input * slope + intercept

    loss = mean_square_error(y_input, y_pred)

    assert loss.close_to(8.8209)

    loss.backward()
    assert slope.grad is not None
    assert intercept.grad is not None
    assert slope.grad.close_to([-5.94])
    assert intercept.grad.close_to([-5.94])


def test_single_lr_step_with_multiple_datapoints():
    # sourcery skip: extract-duplicate-method
    x = [[1], [2]]
    y = [[3], [5]]
    correct_loss = to_tensor([[8.8209], [24.5025]])
    slope = to_tensor([0.02])
    intercept = to_tensor([0.01])

    x_input = to_tensor(x, requires_grad=False, name="x", is_vector=True)
    y_input = to_tensor(y, requires_grad=False, name="y", is_vector=True)

    y_pred = x_input * slope + intercept
    loss = mean_square_error(y_input, y_pred)

    assert loss.close_to(correct_loss)

    old_slope = copy(slope.grad) if slope.grad is not None else 0
    loss.backward()

    logger.info(f"{slope.grad}, {slope.grad - old_slope}")

    correct = to_tensor([[-5.94], [-19.8]])
    assert slope.grad is not None
    assert slope.grad.close_to(correct)

    correct = to_tensor([[-5.94], [-9.9]])
    assert intercept.grad is not None
    assert intercept.grad.close_to(correct)


def test_can_linear_regression():
    np.random.seed(42)

    n = 4
    learning_rate = 3e-3
    learning_rate /= n
    x = np.linspace(-10, 10, n)
    y = x * 2 + 1 + np.random.normal(loc=0, scale=0.01, size=n)

    x = to_tensor(x.reshape(-1, 1), requires_grad=False, name="x")
    y = to_tensor(y.reshape(-1, 1), requires_grad=False, name="y")

    slope = to_tensor([0.02], name="slope")
    intercept = to_tensor([0.0], name="intercept")

    def slope_derivative(x, y, slope, intercept):
        return -2 * (y - x * slope - intercept) * x

    def intercept_derivative(x, y, slope, intercept):
        return -2 * (y - x * slope - intercept)

    losses = [0] * 100
    intercepts = []
    slopes = []
    for idx in range(100):
        last_slope_grad = np.array([0])
        last_intercept_grad = np.array([0])
        for x_input, y_input in zip(x, y):
            x_input = to_tensor(x_input, requires_grad=False, name="x")
            y_input = to_tensor(y_input, requires_grad=False, name="y")
            y_pred = x_input * slope + intercept
            loss = mean_square_error(y_input, y_pred)
            losses[idx] += loss

            loss.backward()

            slope_grad = slope_derivative(x_input, y_input, slope, intercept)
            intercept_grad = intercept_derivative(
                x_input, y_input, slope, intercept
            )
            assert np.allclose(
                slope.grad, last_slope_grad + slope_grad
            ), f"{slope.grad=}, {last_slope_grad=}, {slope_grad=}"
            assert np.allclose(
                intercept.grad, last_intercept_grad + intercept_grad
            ), f"{intercept.grad=}, {last_intercept_grad=}, {intercept_grad=}"

            last_slope_grad = slope.grad
            last_intercept_grad = intercept.grad

        slope -= slope.grad * learning_rate
        intercept -= intercept.grad * learning_rate

        slopes.append(slope)
        intercepts.append(intercept)
        slope = to_tensor(slope, name="slope")
        intercept = to_tensor(intercept, name="intercept")

    assert losses[-1] < 1.5
    assert np.allclose(slope[0], 2, atol=0.01)
    # The intercept takes much longer to tune
    assert intercept[0] > 0.4


@slow_test
def test_linear_regression_real_data():
    X, y = load_diabetes(return_X_y=True)
    x_scaler = RobustScaler()
    y_scaler = RobustScaler()
    X = x_scaler.fit_transform(X)
    y = y_scaler.fit_transform(y.reshape(-1, 1))

    X = to_tensor(X)
    y = to_tensor(y)

    loops = 100
    learning_rate = 1e-1
    n = len(X)
    learning_rate /= n

    slope = init_xavier((X.shape[1], 1))
    intercept = to_tensor([0], name="intercept")

    for _ in range(loops):
        for x_in, y_in in zip(X, y):
            y_pred = Einsum("i,ij->j")(x_in, slope) + intercept
            loss = mean_square_error(y_in, y_pred)
            loss.backward()

        slope = to_tensor(slope - slope.grad * learning_rate, name="slope")
        intercept = to_tensor(
            intercept - intercept.grad * learning_rate, name="intercept"
        )

    predicted = X @ np.array(slope) + intercept[0]
    r_square = r_squared(np.array(y), predicted)
    assert r_square > 0.45


def test_linear_regression_multi_input_output():
    X, y = load_linnerud(return_X_y=True)
    x_scaler = RobustScaler()
    y_scaler = RobustScaler()
    X = x_scaler.fit_transform(X)
    y = y_scaler.fit_transform(y)

    learning_rate = 1e-0
    n = len(X)
    learning_rate /= n
    loops = 100

    slope = init_xavier((X.shape[1], y.shape[1]), name="slope")
    intercept = to_tensor([-0.01, 0.01, 0.02], name="intercept")

    losses: list[np.ndarray | int] = [0] * loops

    def model(X, slope, intercept):
        return Einsum("i,ij->j")(X, slope) + intercept

    for idx in range(loops):
        X = to_tensor(X.copy()).to_vector()
        y = to_tensor(y.copy()).to_vector()

        # predict an output
        y_pred = model(X, slope, intercept)

        # calculate the loss
        loss = mean_square_error(y, y_pred)
        # we need to unvectorise the loss before finding its average
        loss = loss.from_vector().e("a->") / n

        losses[idx] = loss.numpy()
        loss.backward()

        assert slope.grad is not None
        assert intercept.grad is not None

        slope.grad = slope.grad.from_vector().e("abc->bc")
        intercept.grad = intercept.grad.from_vector().e("ab->b")

        slope = to_tensor(slope - slope.grad * learning_rate, name="slope")
        intercept = to_tensor(
            intercept - intercept.grad * learning_rate, name="intercept"
        )

    # the loss should plateau at around 0.5
    assert losses[-1] < 0.6


@slow_test
def test_cross_entropy():
    X, y = load_iris(return_X_y=True)
    x_scaler = RobustScaler()
    X = x_scaler.fit_transform(X)

    # one hot encode y
    y = np.eye(3)[y.astype(int)]

    X = to_tensor(X)
    y = to_tensor(y)

    learning_rate = 1e0
    n = len(X)
    learning_rate /= n
    loops = 100

    slope = init_xavier((X.shape[1], y.shape[1]), name="slope")
    intercept = to_tensor([-0.01, 0.01, 0.02], name="intercept")

    losses = [0] * loops
    for idx in range(loops):
        for x_in, y_in in zip(X, y):
            y_pred = Einsum("i,ij->j")(x_in, slope) + intercept
            loss = cross_entropy(y_in, y_pred)
            losses[idx] += loss
            loss.backward()

        slope = to_tensor(slope - slope.grad * learning_rate, name="slope")
        intercept = to_tensor(
            intercept - intercept.grad * learning_rate, name="intercept"
        )

    assert losses[-1] < 35


@slow_test
def test_cross_entropy_minibatch():
    np.random.seed(42)

    def dataset(X, y, batch_size):
        while True:
            indices = np.arange(len(X))
            batch_indices = np.random.choice(
                indices, size=batch_size, replace=False
            )
            yield zip(X[batch_indices], y[batch_indices])

    X, y = load_iris(return_X_y=True)
    x_scaler = RobustScaler()
    X = x_scaler.fit_transform(X)
    y = np.eye(3)[y.astype(int)]

    learning_rate = 1e0
    learning_rate /= 16
    loops = 500

    slope = init_xavier((X.shape[1], y.shape[1]), name="slope")
    intercept = to_tensor([-0.01, 0.01, 0.02], name="intercept")

    losses = []
    for idx, batch in enumerate(dataset(X, y, batch_size=16)):
        if idx > loops:
            break
        batch_loss = 0
        for x_in, y_in in batch:
            x_in = to_tensor(x_in)
            y_in = to_tensor(y_in)

            y_pred = Einsum("i,ij->j")(x_in, slope) + intercept
            loss = cross_entropy(y_in, y_pred)
            batch_loss += loss
            loss.backward()

        losses.append(batch_loss)

        slope = to_tensor(slope - slope.grad * learning_rate, name="slope")
        intercept = to_tensor(
            intercept - intercept.grad * learning_rate, name="intercept"
        )

    losses = list(smooth(losses, 0.99))
    assert losses[-1] < 6

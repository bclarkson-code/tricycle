import numpy as np

from tricycle.activation import ReLU
from tricycle.einsum import Einsum
from tricycle.functions import Softmax
from tricycle.layers import Dense, Sequential
from tricycle.loss import CrossEntropy, mean_square_error
from tricycle.tensor import to_tensor, unvectorise, vectorise


def test_can_vectorise_single_einsum():
    input_1 = np.arange(1, 4)
    input_2 = np.arange(2, 5)
    input_3 = np.arange(3, 6)

    op = Einsum("a->")

    output_1 = op(to_tensor(input_1))
    output_2 = op(to_tensor(input_2))
    output_3 = op(to_tensor(input_3))

    assert output_1 == 6
    assert output_2 == 9
    assert output_3 == 12

    input_vector = to_tensor([input_1, input_2, input_3])
    input_vector = vectorise(input_vector)
    op = Einsum("a->")
    output_vector = op(input_vector)
    output_vector = unvectorise(output_vector)

    assert output_vector.close_to([6, 9, 12])


def test_can_vectorise_entire_model():
    np.random.seed(42)
    layer_1 = Dense(4, 16)
    layer_2 = Dense(16, 3)
    relu = ReLU()
    model = Sequential(layer_1, relu, layer_2)

    input_1 = np.arange(1, 5)
    input_2 = np.arange(2, 6)
    input_3 = np.arange(3, 7)

    output_1 = model(to_tensor(input_1))
    output_2 = model(to_tensor(input_2))
    output_3 = model(to_tensor(input_3))

    input_vector = to_tensor([input_1, input_2, input_3])
    correct_output = to_tensor(
        [output_1._data, output_2._data, output_3._data]
    )

    input_vector = vectorise(input_vector)
    correct_output = vectorise(correct_output)
    output_vector = model(input_vector)
    output_vector = unvectorise(output_vector)

    assert output_vector.close_to(correct_output)


def test_can_vectorise_mse():
    y_true = to_tensor([0, 0, 1, 0])

    input_1 = to_tensor(np.arange(1, 5))
    input_2 = to_tensor(np.arange(2, 6))
    input_3 = to_tensor(np.arange(3, 7))

    output_1 = mean_square_error(y_true, input_1)
    output_2 = mean_square_error(y_true, input_2)
    output_3 = mean_square_error(y_true, input_3)

    input_y_true = to_tensor(np.array([y_true._data] * 3))
    input_vector = to_tensor(
        np.array([input_1._data, input_2._data, input_3._data])
    )
    correct_output = to_tensor(
        np.array([output_1._data, output_2._data, output_3._data]).sum()
    )

    input_y_true = vectorise(input_y_true)
    input_vector = vectorise(input_vector)
    output_vector = mean_square_error(input_y_true, input_vector)
    output_vector = unvectorise(output_vector)

    assert output_vector.close_to(correct_output)


def test_can_vectorise_cross_entropy():
    y_true = to_tensor([0, 0, 1, 0])
    input_1 = to_tensor(np.arange(1, 5))
    input_2 = to_tensor(np.arange(2, 6))
    input_3 = to_tensor(np.arange(3, 7))

    output_1 = CrossEntropy()(y_true, input_1)
    output_2 = CrossEntropy()(y_true, input_2)
    output_3 = CrossEntropy()(y_true, input_3)

    input_y_true = to_tensor(np.array([y_true._data] * 3))
    input_vector = to_tensor(
        np.array([input_1._data, input_2._data, input_3._data])
    )
    correct_output = to_tensor(
        np.array([output_1._data, output_2._data, output_3._data])
    )

    input_y_true = vectorise(input_y_true)
    input_vector = vectorise(input_vector)
    output_vector = CrossEntropy()(input_y_true, input_vector)
    output_vector = unvectorise(output_vector)

    assert output_vector.close_to(correct_output)


def test_can_vectorise_softmax():
    input_1 = to_tensor(np.arange(1, 5))
    input_2 = to_tensor(np.arange(2, 6))
    input_3 = to_tensor(np.arange(3, 7))

    output_1 = Softmax()(input_1)
    output_2 = Softmax()(input_2)
    output_3 = Softmax()(input_3)

    input_vector = to_tensor(
        np.array([input_1._data, input_2._data, input_3._data])
    )
    correct_output = to_tensor(
        np.array([output_1._data, output_2._data, output_3._data])
    )

    input_vector = vectorise(input_vector)
    output_vector = Softmax()(input_vector)
    output_vector = unvectorise(output_vector)

    assert output_vector.close_to(correct_output)


def test_can_vectorise_split():
    in_tensor = to_tensor(
        [[1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 6]], name="in_tensor"
    )

    out_tensors = in_tensor.to_vector().split(3)

    assert len(out_tensors) == 3
    assert out_tensors[0].shape == (2, 2)
    assert out_tensors[1].shape == (2, 2)
    assert out_tensors[2].shape == (2, 2)

    assert out_tensors[0].close_to([[1, 2], [1, 2]])
    assert out_tensors[1].close_to([[3, 4], [3, 4]])
    assert out_tensors[2].close_to([[5, 6], [5, 6]])

    assert out_tensors[0].is_vector
    assert out_tensors[1].is_vector
    assert out_tensors[2].is_vector

    out_tensors[0].backward()

    assert in_tensor.grad is not None
    assert in_tensor.grad.close_to([[1, 1, 0, 0, 0, 0], [1, 1, 0, 0, 0, 0]])

from os import getcwd, chdir
from shutil import rmtree
from os.path import exists
from tempfile import mkdtemp
import pytest
import numpy as np
import coremltools as ct
import os

from coremltools._deps import (
    _HAS_TF_1,
    _HAS_TF_2,
    _HAS_TORCH,
    MSG_TF1_NOT_FOUND,
    MSG_TF2_NOT_FOUND,
    MSG_TORCH_NOT_FOUND,
)


###############################################################################
# Note: all tests are also used as examples such as in readme.md as a reference
# Whenever any of the following test fails, we should update API documentations
# Each test case is expected to be runnable and self-complete, then sync to the
# documentation pages as API example code snippet.
###############################################################################


@pytest.mark.skipif(not _HAS_TF_1, reason=MSG_TF1_NOT_FOUND)
@pytest.mark.skipif(ct.utils._macos_version() < (10, 15), reason='Model produces specification 4.')
class TestTensorFlow1ConverterExamples:

    @staticmethod
    def test_convert_from_frozen_graph(tmpdir):
        import tensorflow as tf

        with tf.Graph().as_default() as graph:
            x = tf.placeholder(tf.float32, shape=(1, 2, 3), name="input")
            y = tf.nn.relu(x, name="output")

        mlmodel = ct.convert(graph)

        test_input = np.random.rand(1, 2, 3) - 0.5
        with tf.compat.v1.Session(graph=graph) as sess:
            expected_val = sess.run(y, feed_dict={x: test_input})
        results = mlmodel.predict({"input": test_input})
        np.testing.assert_allclose(results["output"], expected_val)

    @staticmethod
    def test_convert_from_frozen_graph_file(tmpdir):
        # create the model to convert
        import tensorflow as tf

        # write a toy frozen graph
        # Note that we usually needs to run freeze_graph() on tf.Graph()
        # skipping here as this toy model does not contain any variables
        with tf.Graph().as_default() as graph:
            x = tf.placeholder(tf.float32, shape=(1, 2, 3), name="input")
            y = tf.nn.relu(x, name="output")

        save_path = str(tmpdir)
        tf.io.write_graph(graph, save_path, "frozen_graph.pb", as_text=False)

        # Create a test sample
        # -0.5 to have some negative values
        test_input = np.random.rand(1, 2, 3) - 0.5
        with tf.compat.v1.Session(graph=graph) as sess:
            expected_val = sess.run(y, feed_dict={x: test_input})

        # The input `.pb` file is a frozen graph format that usually
        # generated by TensorFlow's utility function `freeze_graph()`
        pb_path = os.path.join(save_path, "frozen_graph.pb")

        # 3 ways to specify inputs:
        # (1) Fully specify inputs
        mlmodel = ct.convert(
            pb_path,
            # We specify inputs with name matching the placeholder name.
            inputs=[ct.TensorType(name="input", shape=(1, 2, 3))],
            outputs=["output"],
        )

        # (2) Specify input TensorType without name (when there's only one
        # input)
        mlmodel = ct.convert(
            pb_path,
            # TensorType name is optional when there's only one input.
            inputs=[ct.TensorType(shape=(1, 2, 3))],
            outputs=["output"],
        )

        # (3) Not specify inputs at all. `inputs` is optional for TF. When
        # inputs is not specified, convert() infers inputs from Placeholder
        # nodes.
        mlmodel = ct.convert(pb_path, outputs=["output"])

        results = mlmodel.predict({"input": test_input})
        np.testing.assert_allclose(results["output"], expected_val)
        mlmodel_path = os.path.join(save_path, "model.mlmodel")
        # Save the converted model
        mlmodel.save(mlmodel_path)

        results = mlmodel.predict({"input": test_input})
        np.testing.assert_allclose(results["output"], expected_val)

    @staticmethod
    def test_convert_from_saved_model_dir(tmpdir):
        # Sample input
        test_input = np.random.rand(1, 3, 5) - 0.5

        # create the model to convert
        import tensorflow as tf

        with tf.compat.v1.Session() as sess:
            x = tf.placeholder(shape=(1, 3, 5), dtype=tf.float32)
            y = tf.nn.relu(x)

            expected_val = sess.run(y, feed_dict={x: test_input})

        # Save model as SavedModel
        inputs = {"x": x}
        outputs = {"y": y}
        save_path = str(tmpdir)
        tf.compat.v1.saved_model.simple_save(sess, save_path, inputs, outputs)

        # SavedModel directory generated by TensorFlow 1.x
        # when converting from SavedModel dir, inputs / outputs are optional
        mlmodel = ct.convert(save_path)

        # Need input output names to call mlmodel
        # x.name == 'Placeholder:0'. Strip out ':0'
        input_name = x.name.split(":")[0]
        results = mlmodel.predict({input_name: test_input})
        # y.name == 'Relu:0'. output_name == 'Relu'
        output_name = y.name.split(":")[0]
        np.testing.assert_allclose(results[output_name], expected_val)


@pytest.mark.skipif(not _HAS_TF_2, reason=MSG_TF2_NOT_FOUND)
@pytest.mark.skipif(ct.utils._macos_version() < (10, 15), reason='Model produces specification 4.')
class TestTensorFlow2ConverterExamples:
    def setup_class(self):
        self._cwd = getcwd()
        self._temp_dir = mkdtemp()
        # step into temp directory as working directory
        # to make the user-facing examples cleaner
        chdir(self._temp_dir)

        # create toy models for conversion examples
        import tensorflow as tf

        # write a toy tf.keras HDF5 model
        tf_keras_model = tf.keras.Sequential(
            [
                tf.keras.layers.Flatten(input_shape=(28, 28)),
                tf.keras.layers.Dense(128, activation=tf.nn.relu),
                tf.keras.layers.Dense(10, activation=tf.nn.softmax),
            ]
        )
        tf_keras_model.save("./tf_keras_model.h5")

        # write a toy SavedModel directory
        tf_keras_model.save("./saved_model", save_format="tf")

    def teardown_class(self):
        chdir(self._cwd)
        if exists(self._temp_dir):
            rmtree(self._temp_dir)

    @staticmethod
    def test_convert_tf_keras_h5_file(tmpdir):
        import tensorflow as tf

        x = tf.keras.Input(shape=(32,), name="input")
        y = tf.keras.layers.Dense(16, activation="softmax")(x)
        keras_model = tf.keras.Model(x, y)
        save_dir = str(tmpdir)
        h5_path = os.path.join(save_dir, "tf_keras_model.h5")
        keras_model.save(h5_path)

        mlmodel = ct.convert(h5_path)

        test_input = np.random.rand(2, 32)
        expected_val = keras_model(test_input)
        results = mlmodel.predict({"input": test_input})
        np.testing.assert_allclose(results["Identity"], expected_val, rtol=1e-4)

    @staticmethod
    def test_convert_tf_keras_model():
        import tensorflow as tf

        x = tf.keras.Input(shape=(32,), name="input")
        y = tf.keras.layers.Dense(16, activation="softmax")(x)
        keras_model = tf.keras.Model(x, y)

        mlmodel = ct.convert(keras_model)

        test_input = np.random.rand(2, 32)
        expected_val = keras_model(test_input)
        results = mlmodel.predict({"input": test_input})
        np.testing.assert_allclose(results["Identity"], expected_val, rtol=1e-4)

    @staticmethod
    def test_convert_tf_keras_applications_model():
        import tensorflow as tf

        tf_keras_model = tf.keras.applications.MobileNet(
            weights="imagenet", input_shape=(224, 224, 3)
        )

        # inputs / outputs are optional, we can get from tf.keras model
        # this can be extremely helpful when we want to extract sub-graphs
        input_name = tf_keras_model.inputs[0].name.split(":")[0]
        # note that the `convert()` requires tf.Graph's outputs instead of
        # tf.keras.Model's outputs, to access that, we can do the following
        output_name = tf_keras_model.outputs[0].name.split(":")[0]
        tf_graph_output_name = output_name.split("/")[-1]

        mlmodel = ct.convert(
            tf_keras_model,
            inputs=[ct.TensorType(name=input_name, shape=(1, 224, 224, 3))],
            outputs=[tf_graph_output_name],
        )
        mlmodel.save("./mobilenet.mlmodel")

    @staticmethod
    def test_convert_from_saved_model_dir():
        # SavedModel directory generated by TensorFlow 2.x
        mlmodel = ct.convert("./saved_model")
        mlmodel.save("./model.mlmodel")


@pytest.mark.skipif(not _HAS_TORCH, reason=MSG_TORCH_NOT_FOUND)
@pytest.mark.skipif(ct.utils._macos_version() < (10, 15), reason='Model produces specification 4.')
class TestPyTorchConverterExamples:
    @staticmethod
    def test_convert_torch_vision_mobilenet_v2(tmpdir):
        import torch
        import torchvision

        """
        In this example, we'll instantiate a PyTorch classification model and convert
        it to Core ML.
        """

        """
        Here we instantiate our model. In a real use case this would be your trained
        model.
        """
        model = torchvision.models.mobilenet_v2()

        """
        The next thing we need to do is generate TorchScript for the model. The easiest
        way to do this is by tracing it.
        """

        """
        It's important that a model be in evaluation mode (not training mode) when it's
        traced. This makes sure things like dropout are disabled.
        """
        model.eval()

        """
        Tracing takes an example input and traces its flow through the model. Here we
        are creating an example image input.

        The rank and shape of the tensor will depend on your model use case. If your
        model expects a fixed size input, use that size here. If it can accept a
        variety of input sizes, it's generally best to keep the example input small to
        shorten how long it takes to run a forward pass of your model. In all cases,
        the rank of the tensor must be fixed.
        """
        example_input = torch.rand(1, 3, 256, 256)

        """
        Now we actually trace the model. This will produce the TorchScript that the
        CoreML converter needs.
        """
        traced_model = torch.jit.trace(model, example_input)

        """
        Now with a TorchScript representation of the model, we can call the CoreML
        converter. The converter also needs a description of the input to the model,
        where we can give it a convenient name.
        """
        mlmodel = ct.convert(
            traced_model,
            inputs=[ct.TensorType(name="input", shape=example_input.shape)],
        )

        """
        Now with a conversion complete, we can save the MLModel and run inference.
        """
        save_path = os.path.join(str(tmpdir), "mobilenet_v2.mlmodel")
        mlmodel.save(save_path)

        """
        Running predict() is only supported on macOS.
        """
        if ct.utils._is_macos():
            results = mlmodel.predict({"input": example_input.numpy()})
            expected = model(example_input)
            np.testing.assert_allclose(
                list(results.values())[0], expected.detach().numpy(), rtol=1e-2
            )

    @staticmethod
    def test_int64_inputs():
        import torch

        num_tokens = 3
        embedding_size = 5

        class TestModule(torch.nn.Module):
            def __init__(self):
                super(TestModule, self).__init__()
                self.embedding = torch.nn.Embedding(num_tokens, embedding_size)

            def forward(self, x):
                return self.embedding(x)

        model = TestModule()
        model.eval()

        example_input = torch.randint(high=num_tokens, size=(2,), dtype=torch.int64)
        traced_model = torch.jit.trace(model, example_input)
        mlmodel = ct.convert(
            traced_model,
            inputs=[
                ct.TensorType(
                    name="input",
                    shape=example_input.shape,
                    dtype=example_input.numpy().dtype,
                )
            ],
        )

        # running predict() is supported on macOS
        if ct.utils._is_macos():
            result = mlmodel.predict(
                {"input": example_input.detach().numpy().astype(np.float32)}
            )

            # Verify outputs
            expected = model(example_input)
            np.testing.assert_allclose(result["5"], expected.detach().numpy())

        # Duplicated inputs are invalid
        with pytest.raises(ValueError, match=r"Duplicated inputs"):
            mlmodel = ct.convert(
                traced_model,
                inputs=[
                    ct.TensorType(
                        name="input",
                        shape=example_input.shape,
                        dtype=example_input.numpy().dtype,
                    ),
                    ct.TensorType(
                        name="input",
                        shape=example_input.shape,
                        dtype=example_input.numpy().dtype,
                    ),
                ],
            )

        # Outputs must not be specified for PyTorch
        with pytest.raises(ValueError, match=r"outputs must not be specified"):
            mlmodel = ct.convert(
                traced_model,
                inputs=[
                    ct.TensorType(
                        name="input",
                        shape=example_input.shape,
                        dtype=example_input.numpy().dtype,
                    ),
                ],
                outputs=["output"],
            )


class TestMILExamples:
    @staticmethod
    def test_tutorial():
        from coremltools.converters.mil import Builder as mb

        @mb.program(
            input_specs=[mb.TensorSpec(shape=(1, 100, 100, 3)),]
        )
        def prog(x):
            x = mb.relu(x=x, name="relu")
            x = mb.transpose(x=x, perm=[0, 3, 1, 2], name="transpose")
            x = mb.reduce_mean(x=x, axes=[2, 3], keep_dims=False, name="reduce")
            x = mb.log(x=x, name="log")
            y = mb.add(x=1, y=2)
            return x

        print("prog:\n", prog)

        # Convert and verify
        from coremltools.converters.mil.converter import _convert
        from coremltools import models

        proto = _convert(prog, convert_from="mil")

        model = models.MLModel(proto)

        # running predict() is only supported on macOS
        if ct.utils._is_macos():
            prediction = model.predict(
                {"x": np.random.rand(1, 100, 100, 3).astype(np.float32),}
            )
            assert len(prediction) == 1

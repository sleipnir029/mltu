import os
import logging
import numpy as np
from datetime import datetime

import torch.onnx
from torch.utils.tensorboard import SummaryWriter

class Callback:
    """ Base class used to build new callbacks."""
    def __init__(
        self, 
        monitor: str = "val_loss"
    ) -> None:
        self.monitor = monitor
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

    def on_train_begin(self, logs=None):
        pass

    def on_train_end(self, logs=None):
        pass

    def on_train_batch_begin(self, batch: int, logs=None):
        pass

    def on_train_batch_end(self, batch: int, logs=None):
        pass

    def on_test_begin(self, logs=None):
        pass

    def on_test_end(self, logs=None):
        pass

    def on_test_batch_begin(self, batch: int, logs=None):
        pass

    def on_test_batch_end(self, batch: int, logs=None):
        pass

    def on_epoch_begin(self, epoch: int, logs=None):
        pass

    def on_epoch_end(self, epoch: int, logs=None):
        pass

    def on_batch_begin(self, batch: int, logs=None):
        pass

    def on_batch_end(self, batch: int, logs=None):
        pass

    def get_monitor_value(self, logs: dict):
        logs = logs or {}
        monitor_value = logs.get(self.monitor)
        if monitor_value is None:
            logging.warning(
                "Early stopping conditioned on metric `%s` "
                "which is not available. Available metrics are: %s",
                self.monitor,
                ",".join(list(logs.keys())),
            )
        return monitor_value

class EarlyStopping(Callback):
    def __init__(
        self, 
        monitor: str = "val_loss",
        min_delta: float = 0.0, 
        patience: int = 0, 
        verbose: bool = False,
        mode: str = "max_equal",
        ):
        super(EarlyStopping, self).__init__()

        self.monitor = monitor
        self.min_delta = min_delta
        self.patience = patience
        self.verbose = verbose
        self.mode = mode
        self.wait = None
        self.stopped_epoch = None
        self.best = None

        if self.mode not in ["min", "max", "max_equal", "min_equal"]:
            raise ValueError(
                "EarlyStopping mode %s is unknown, "
                "please choose one of min, max, max_equal, min_equal" % self.mode
            )
        
    def on_train_begin(self, logs=None):
        self.wait = 0
        self.stopped_epoch = 0
        self.best = np.inf if self.mode == "min" or self.mode == "min_equal" else -np.Inf

    def on_epoch_end(self, epoch: int, logs=None):
        current = self.get_monitor_value(logs)
        if current is None:
            return

        if self.mode == "min" and np.less(current, self.best - self.min_delta):
            self.best = current
            self.wait = 0
        elif self.mode == "max" and np.greater(current, self.best + self.min_delta):
            self.best = current
            self.wait = 0
        elif self.mode == "min_equal" and np.less_equal(current, self.best - self.min_delta):
            self.best = current
            self.wait = 0
        elif self.mode == "max_equal" and np.greater_equal(current, self.best + self.min_delta):
            self.best = current
            self.wait = 0
        else:
            self.wait += 1
            if self.wait >= self.patience:
                self.stopped_epoch = epoch
                self.model.stop_training = True

    def on_train_end(self, logs=None):
        if self.stopped_epoch > 0 and self.verbose:
            self.logger.info(f"Epoch {self.stopped_epoch}: early stopping")


class ModelCheckpoint(Callback):
    """ ModelCheckpoint callback to save the model after every epoch or the best model across all epochs."""
    def __init__(
        self, 
        filepath: str,
        monitor: str = "val_loss",
        verbose: bool = False,
        save_best_only: bool = True,
        mode: str = "min",
        ) -> None:
        """ ModelCheckpoint callback to save the model after every epoch or the best model across all epochs
        
        Args:
            filepath (str): path to save the model file
            monitor (str, optional): metric to monitor. Defaults to "val_loss".
            verbose (bool, optional): verbosity mode. Defaults to False.
            save_best_only (bool, optional): if True, the latest best model according to the quantity monitored will not be overwritten. Defaults to True.
            mode (str, optional): one of {min, max, max_equal, min_equal}. Defaults to "min".
        """
        super(ModelCheckpoint, self).__init__()

        self.filepath = filepath
        self.monitor = monitor
        self.verbose = verbose
        self.mode = mode
        self.save_best_only = save_best_only
        self.best = None

        if self.mode not in ["min", "max", "max_equal", "min_equal"]:
            raise ValueError(
                "ModelCheckpoint mode %s is unknown, "
                "please choose one of min, max, max_equal, min_equal" % self.mode
            )
        
        if self.mode == "min": self.monitor_op = np.less
        elif self.mode == "max": self.monitor_op = np.greater
        elif self.mode == "min_equal": self.monitor_op = np.less_equal
        elif self.mode == "max_equal": self.monitor_op = np.greater_equal
        
    def on_train_begin(self, logs=None):
        self.best = np.inf if self.mode == "min" or self.mode == "min_equal" else -np.Inf

        # create directory if not exist
        if not os.path.exists(os.path.dirname(self.filepath)):
            os.makedirs(os.path.dirname(self.filepath))

    def on_epoch_end(self, epoch: int, logs=None):
        current = self.get_monitor_value(logs)
        if current is None:
            return

        if self.monitor_op(current, self.best):
            previous = self.best
            self.best = current
            self.save_model(epoch, current, previous)
        else:
            if not self.save_best_only:
                self.save_model(epoch, current, previous=None)

    def save_model(self, epoch: int, best: float, previous: float = None):
        """ Save model to filepath
        
        Args:
            epoch (int): current epoch
            best (float): current best value
            previous (float, optional): previous best value. Defaults to None.
        """
        if self.verbose:
            if previous is None:
                self.logger.info(f"Epoch {epoch}: {self.monitor} got {best:.5f}, saving model to {self.filepath}")
            else:
                self.logger.info(f"Epoch {epoch}: {self.monitor} improved from {previous:.5f} to {best:.5f}, saving model to {self.filepath}")

        self.model.save(self.filepath)


class TensorBoard(Callback):
    """ TensorBoard basic visualizations. """
    def __init__(self, log_dir: str = "logs", comment: str = None):
        """ TensorBoard basic visualizations.
        
        Args:
            log_dir (str, optional): the path of the directory where to save the log files to be parsed by TensorBoard. Defaults to "logs".
            comment (str, optional): comment to append to the default log_dir. Defaults to None.
        """
        super(TensorBoard, self).__init__()

        self.log_dir = log_dir

        self.writer = None
        self.comment = str(comment) if not None else datetime.now().strftime("%Y%m%d-%H%M%S")

    def on_train_begin(self, logs=None):
        if self.writer is None:
            self.writer = SummaryWriter(self.log_dir, comment=self.comment)

    def update_lr(self, epoch: int):
        for param_group in self.model.optimizer.param_groups:
            self.writer.add_scalar("learning_rate", param_group["lr"], epoch)

    def update_histogram(self, epoch: int):
        for name, param in self.model.model.named_parameters():
            self.writer.add_histogram(name, param.clone().cpu().data.numpy(), epoch)

    def parse_key(self, key: str):
        if key.startswith("val_"):
            return f"{key[4:].capitalize()}/test"
        else:
            return f"{key.capitalize()}/train"

    def on_epoch_end(self, epoch: int, logs=None):
        logs = logs or {}
        for key, value in logs.items():
            self.writer.add_scalar(self.parse_key(key), value, epoch)

        self.update_lr(epoch)
        self.update_histogram(epoch)

    def on_train_end(self, logs=None):
        self.writer.close()


class Model2onnx(Callback):
    """Converts the model from PyTorch to ONNX format after training."""
    def __init__(
        self, 
        saved_model_path: str,
        input_shape: tuple,
        export_params: bool=True,
        opset_version: int=14,
        do_constant_folding: bool=True,
        input_names: list=['input'],
        output_names: list=['output'],
        dynamic_axes: dict={'input' : {0 : 'batch_size'}, 
                            'output' : {0 : 'batch_size'}},
        verbose: bool=False,
        metadata: dict=None,
        ) -> None:
        """ Converts the model from PyTorch to ONNX format after training.

        Args:
            saved_model_path (str): path to the saved model
            input_shape (tuple): input shape of the model
            export_params (bool, optional): if True, all model parameters will be exported. Defaults to True.
            opset_version (int, optional): the ONNX version to export the model to. Defaults to 14.
            do_constant_folding (bool, optional): whether to execute constant folding for optimization. Defaults to True.
            input_names (list, optional): the model's input names. Defaults to ['input'].
            output_names (list, optional): the model's output names. Defaults to ['output'].
            dynamic_axes (dict, optional): dictionary specifying dynamic axes. Defaults to {'input' : {0 : 'batch_size'}, 'output' : {0 : 'batch_size'}}.
            verbose (bool, optional): if True, information about the conversion will be printed. Defaults to False.
            metadata (dict, optional): dictionary containing model metadata. Defaults to None.
        """
        super().__init__()
        self.saved_model_path = saved_model_path
        self.input_shape = input_shape
        self.export_params = export_params
        self.opset_version = opset_version
        self.do_constant_folding = do_constant_folding
        self.input_names = input_names
        self.output_names = output_names
        self.dynamic_axes = dynamic_axes
        self.verbose = verbose
        self.metadata = metadata
        
        self.onnx_model_path = saved_model_path.replace(".pt", ".onnx")

    def on_train_end(self, logs=None):
        self.model.model.load_state_dict(torch.load(self.saved_model_path))

        # place model on cpu
        self.model.model.to("cpu")

        # set the model to inference mode
        self.model.model.eval()
        
        # convert the model to ONNX format
        dummy_input = torch.randn(self.input_shape)

        # Export the model
        torch.onnx.export(
            self.model.model,               
            dummy_input,                         
            self.onnx_model_path,   
            export_params=self.export_params,        
            opset_version=self.opset_version,          
            do_constant_folding=self.do_constant_folding,  
            input_names = self.input_names,   
            output_names = self.output_names, 
            dynamic_axes = self.dynamic_axes,
            )
        
        if self.verbose:
            self.logger.info(f"Model saved to {self.onnx_model_path}")

        if self.metadata and isinstance(self.metadata, dict):
            import onnx

            # Load the ONNX model
            onnx_model = onnx.load(self.onnx_model_path)

            # Add the metadata dictionary to the model's metadata_props attribute
            for key, value in self.metadata.items():
                meta = onnx_model.metadata_props.add()
                meta.key = key
                meta.value = value

            # Save the modified ONNX model
            onnx.save(onnx_model, self.onnx_model_path)
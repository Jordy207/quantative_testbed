from __future__ import annotations
import logging
from collections import OrderedDict
from pathlib import Path
from typing import Union, Type

import deprecate
import torch
from torch.utils.tensorboard import SummaryWriter

from fltk.util.results import EpochData
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fltk.util.config import DistributedConfig


def flatten_params(model_description: Union[torch.nn.Module, OrderedDict]):
    """
    flattens all parameters into a single column vector. Returns the dictionary to recover them
    :param: parameters: a generator or list of all the parameters
    :return: a dictionary: {"params": [#params, 1],
    "indices": [(start index, end index) for each param] **Note end index in uninclusive**
    """
    if isinstance(model_description, torch.nn.Module):
        parameters = model_description.parameters()
    else:
        parameters = model_description.values()
    parameter_list = [torch.flatten(p) for p in parameters]  # pylint: disable=no-member
    flat_params = torch.cat(parameter_list).view(-1, 1)  # pylint: disable=no-member
    return flat_params


def recover_flattened(flat_params: torch.Tensor, model: torch.nn.Module):
    """
    Gives a list of recovered parameters from their flattened form
    :param flat_params: [#params, 1]
    :param model: the model that gives the params with correct shapes
    :return: the params, reshaped to the ones in the model, with the same order as those in the model
    """
    indices = []
    acc_size = 0
    for param in model.parameters():
        size = param.shape[0]
        indices.append((acc_size, acc_size + size))
        acc_size += size
    recovered_params = [flat_params[acc_size:e] for (acc_size, e) in indices]
    for indx, param in enumerate(model.parameters()):
        recovered_params[indx] = recovered_params[indx].view(*param.shape)
    return recovered_params


def initialize_default_model(conf: DistributedConfig, model_class: Type[torch.nn.Module]) -> torch.nn.Module:
    """
    Load a default model dictionary into a torch model.
    @param conf: Distributed configuration (cluster configuration.
    @type conf: DistributedConfig
    @param model_class: Reference to class implementing the model to be loaded.
    @type model_class: Type[torch.nn.Module]
    @return: M
    @rtype:
    """
    model = model_class()
    default_model_path = f"{conf.get_default_model_folder_path()}/{model_class.__name__}.model"
    model.load_state_dict(torch.load(default_model_path))
    return model


def load_model_from_file(model: torch.nn.Module, model_file_path: Path) -> None:
    """
    Function to load a PyTorch state_dict model file into a network instance, inplace. This requires the model
    file to be of the same type.

    @param model: Instantiated PyTorch module corresponding to the to be loaded network.
    @type model: torch.nn.Module
    @param model_file_path: Path to h5s file generated by PyTorch. Can be generated for a network by using the
    PyTorch torch.save(module.state_dict()) syntax.
    @type model_file_path: Path
    @return: None
    @rtype: None
    """

    if model_file_path.is_file():
        try:
            model.load_state_dict(torch.load(model_file_path))
        except Exception:  # pylint: disable=broad-except
            logging.warning("Couldn't load model. Attempting to map CUDA tensors to CPU to solve error.")
    else:
        logging.warning(f'Could not find model: {model_file_path}')
        raise FileExistsError(f"Cannot load model file {model_file_path} into {model}...")


def save_model(model: torch.nn.Module, directory: str, epoch: int):
    """
    Saves the model if necessary.
    """
    full_save_path = f"./{directory}/{model.__class__.__name__}_{epoch}.pth"
    torch.save(model.state_dict(), full_save_path)


def test_model(model, epoch, writer: SummaryWriter = None) -> EpochData:
    """
    Function to test model during training with
    @return:
    @rtype:
    """
    # Test interleaved to speed up execution, i.e. don't keep the clients waiting.
    accuracy, loss, class_precision, class_recall = model.test()
    data = EpochData(epoch_id=epoch,
                     duration_train=0,
                     duration_test=0,
                     loss_train=0,
                     accuracy=accuracy,
                     loss=loss,
                     class_precision=class_precision,
                     class_recall=class_recall,
                     confusion_mat=None,
                     num_epochs=0)
    if writer:
        writer.add_scalar('accuracy per epoch', accuracy, epoch)
    return data

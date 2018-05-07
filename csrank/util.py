import inspect
import itertools as iter
import logging
import multiprocessing
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import seaborn as sns
import tensorflow as tf
from keras import backend as K
from matplotlib import pyplot as plt
from scipy.stats import rankdata
from sklearn.covariance import GraphLasso
from tensorflow.python.client import device_lib

from csrank.tunable import Tunable

__all__ = ['check_learner_class', 'configure_logging_numpy_keras', 'create_dir_recursively',
           'create_graph_pairwise_matrix', 'create_pairwise_prob_matrix', 'duration_tillnow', 'files_with_same_name',
           'get_instances_objects', 'get_loss_for_array', 'get_mean_loss_for_dictionary', 'get_rankings_tensor',
           'get_tensor_value', 'heat_map', 'normalize', 'print_dictionary', 'quicksort', 'ranking_ordering_conversion',
           'rename_file_if_exist', 'scores_to_rankings', 'seconds_to_time', 'strongly_connected_components',
           'tensorify', 'time_from_now']


def scores_to_rankings(score_matrix):
    mask3 = np.equal(score_matrix[:, None] - score_matrix[:, :, None], 0)
    n_objects = score_matrix.shape[1]
    ties = np.sum(np.sum(mask3, axis=(1, 2)) - n_objects)
    rankings = np.empty_like(score_matrix)
    if ties > 0:
        for i, s in enumerate(score_matrix):
            rankings[i] = rankdata(s) - 1
    else:
        orderings = np.argsort(score_matrix, axis=1)[:, ::-1]
        rankings = np.argsort(orderings, axis=1)
    return rankings


def ranking_ordering_conversion(input):
    output = np.argsort(input, axis=1)
    return output


def strongly_connected_components(graph):
    """ Find the strongly connected components in a graph using
        Tarjan's algorithm.
        # Taken from http://www.logarithmic.net/pfh-files/blog/01208083168/sort.py

        graph should be a dictionary mapping node names to
        lists of successor nodes.
        """

    result = []
    stack = []
    low = {}

    def visit(node):
        if node in low: return

        num = len(low)
        low[node] = num
        stack_pos = len(stack)
        stack.append(node)

        for successor in graph[node]:
            visit(successor)
            low[node] = min(low[node], low[successor])

        if num == low[node]:
            component = tuple(stack[stack_pos:])
            del stack[stack_pos:]
            result.append(component)
            for item in component:
                low[item] = len(graph)

    for node in graph:
        visit(node)

    return result


def create_graph_pairwise_matrix(matrix):
    n_objects = matrix.shape[0]
    graph = {key: [] for key in np.arange(n_objects)}
    for i, j in iter.combinations(np.arange(n_objects), 2):
        p_ij = matrix[i, j]
        p_ji = matrix[j, i]
        if (p_ij > p_ji):
            graph[j].append(i)
        if (p_ij < p_ji):
            graph[i].append(j)
        if (p_ij == p_ji):
            graph[j].append(i)
            graph[i].append(j)
    return graph


def create_pairwise_prob_matrix(n_objects):
    # Create a non-transitive pairwise probability matrix for n_objects*n_objects
    non_transitive = False
    while (not non_transitive):
        pairwise_prob = np.zeros([n_objects, n_objects])
        for i, j in iter.combinations(np.arange(n_objects), 2):
            pairwise_prob[i, j] = np.random.rand(1)[0]
            pairwise_prob[j, i] = 1.0 - pairwise_prob[i, j]
        for comp in strongly_connected_components(create_graph_pairwise_matrix(pairwise_prob)):
            if (len(comp) >= 3):
                non_transitive = True
                break
    return pairwise_prob


def quicksort(arr, matrix):
    # Apply the quick sort algorithm for the given set of objects and produces a ranking based on provided pairwise matrix
    if len(arr) < 2:
        return arr
    else:
        pivot = arr[0]
        right = [i for i in arr[1:] if matrix[pivot, i] == 1]
        left = [i for i in arr[1:] if matrix[pivot, i] == 0]
        return quicksort(left, matrix) + [pivot] + quicksort(right, matrix)


# Inputs are tensors
def get_rankings_tensor(n_objects, y_pred):
    # indices = orderings
    toprel, orderings = tf.nn.top_k(y_pred, n_objects)
    # indices = rankings
    troprel, rankings = tf.nn.top_k(orderings, n_objects)
    rankings = K.cast(rankings[:, ::-1], dtype='float32')
    return rankings


# Inputs are tensors
def get_instances_objects(y_true):
    n_objects = K.cast(K.int_shape(y_true)[1], 'int32')
    total = K.cast(K.greater_equal(y_true, 0), dtype='int32')
    n_instances = K.cast(tf.reduce_sum(total) / n_objects, dtype='int32')
    return n_instances, n_objects


def tensorify(x):
    """Converts x into a Keras tensor"""
    if not isinstance(x, (tf.Tensor, tf.Variable)):
        return K.constant(x)
    return x


def get_tensor_value(x):
    if isinstance(x, tf.Tensor):
        return K.get_value(x)
    return x


def normalize(score):
    norm = [float(i) / np.sum(score) for i in score]
    norm = [float(i) / np.max(norm) for i in norm]
    return norm


def print_dictionary(dictionary):
    output = "\n"
    for key, value in dictionary.items():
        output = output + str(key) + " => " + str(value) + "\n"
    return output


def create_dir_recursively(path, is_file_path=False):
    if is_file_path:
        path = os.path.dirname(path)
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def rename_file_if_exist(file_path):
    my_file = Path(file_path)
    try:
        extension = '.' + file_path.split('.')[1]
    except IndexError:
        extension = ''
    path = file_path.split('.')[0]
    i = 1
    while my_file.is_file():
        file_path = path + str(i) + extension
        my_file = Path(file_path)
        i += 1
    return file_path


def files_with_same_name(file_path):
    files_list = []
    my_file = Path(file_path)
    try:
        extension = '.' + file_path.split('.')[1]
    except IndexError:
        extension = ''
    path = file_path.split('.')[0]
    i = 1
    while my_file.is_file():
        files_list.append(file_path)
        file_path = path + str(i) + extension
        my_file = Path(file_path)
        i += 1
    return files_list


def setup_logger(log_path=None):
    """Function setup as many loggers as you want"""
    if log_path is None:
        dirname = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
        dirname = os.path.dirname(dirname)
        log_path = os.path.join(dirname, "experiments", "logs", "logs.log")
        create_dir_recursively(log_path, True)

    FORMAT = '%(asctime)s %(name)s %(levelname)-8s %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'
    logging.basicConfig(filename=log_path, level=logging.DEBUG,
                        format=FORMAT,
                        datefmt=datefmt)


def configure_logging_numpy_keras(seed=42, log_path=None):
    setup_logger(log_path=log_path)
    tf.set_random_seed(seed)
    os.environ["KERAS_BACKEND"] = "tensorflow"
    devices = [x.name for x in device_lib.list_local_devices()]
    logger = logging.getLogger("Configure Keras")
    logger.info("Devices {}".format(devices))
    n_gpus = len([x.name for x in device_lib.list_local_devices() if x.device_type == 'GPU'])
    if (n_gpus == 0):
        config = tf.ConfigProto(intra_op_parallelism_threads=1, inter_op_parallelism_threads=1,
                                allow_soft_placement=True, log_device_placement=False,
                                device_count={'CPU': multiprocessing.cpu_count() - 2})
    else:
        config = tf.ConfigProto(allow_soft_placement=True,
                                log_device_placement=True, intra_op_parallelism_threads=2,
                                inter_op_parallelism_threads=2)  # , gpu_options = gpu_options)
    sess = tf.Session(config=config)
    K.set_session(sess)
    np.random.seed(seed)
    logger.info("Number of GPUS {}".format(n_gpus))
    logger.info("log file path: {}".format(log_path))


def duration_tillnow(start):
    return (datetime.now() - start).total_seconds()


def time_from_now(target_time_sec):
    base_datetime = datetime.now()
    delta = timedelta(seconds=target_time_sec)
    target_date = base_datetime + delta
    return target_date.strftime("%Y-%m-%d %H:%M:%S")


def seconds_to_time(target_time_sec):
    return str(timedelta(seconds=target_time_sec))


def get_mean_loss_for_dictionary(logger, metric, Y_true, Y_pred):
    losses = []
    total_instances = 0
    for n, y_pred in Y_pred.items():
        l = get_loss_for_array(metric, Y_true[n], y_pred)
        logger.info('nobj=>{} : loss/acc=>{} : ins=>{}'.format(n, l, y_pred.shape[0]))
        l = l * y_pred.shape[0]
        total_instances += y_pred.shape[0]
        losses.append(l)
    losses = np.array(losses)
    logger.info("total_instances {}".format(total_instances))
    logger.info(losses)
    loss = np.sum(losses) / total_instances
    return loss


def get_loss_for_array(metric, y_true, y_pred):
    x = metric(y_true, y_pred)
    x = tensorify(x)
    return get_tensor_value(K.mean(x))


def heat_map(file_path, X, headers, cmap=sns.color_palette("Blues")):
    model = GraphLasso()
    model.fit(X)
    Cov = model.covariance_
    std = np.diag(1. / np.sqrt(np.diag(Cov)))
    Cor = std.dot(Cov).dot(std)

    fig, ax = plt.subplots()
    # the size of A4 paper
    fig.set_size_inches(10, 8)
    ax = sns.heatmap(Cor, cmap=cmap, square=True, xticklabels=1, yticklabels=1, linewidths=.5)
    ax.set_yticklabels(headers, rotation=0, fontsize=12)
    ax.set_xticklabels(headers, rotation=90, fontsize=12)
    plt.subplots_adjust(bottom=0.4, left=0.2)

    sns.despine(left=True, bottom=True)

    plt.tight_layout()

    plt.savefig(file_path)
    plt.show()


def check_learner_class(ranker):
    """ Function which checks if the ranker is an instance of the :class:`csrank.tunning.Tunable` class
 
    Parameters
    ----------
    ranker: object
        The ranker object to be checked
    """
    if not (isinstance(ranker, Tunable) and hasattr(ranker, 'set_tunable_parameters')):
        logging.error('The given object ranker is not tunable')
        raise AttributeError


def get_duration_seconds(duration):
    time = int(re.findall(r'\d+', duration)[0])
    d = duration.split(str(time))[1].upper()
    options = {"D": 24 * 60 * 60, "H": 60 * 60, "M": 60}
    return options[d] * time

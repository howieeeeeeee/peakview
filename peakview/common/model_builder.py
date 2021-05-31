# -*- coding: utf-8 -*-
"""
    Author  ：   Ethan Chiu
    Time    ：   2021/3/30 下午12:15
    Site    :   
    Suggestion  ：
    Description :
    File    :   model_builder.py
    Software    :   PyCharm
"""
import re
import collections
from collections.abc import Sequence, Mapping, Iterator
import tensorflow as tf
import abc
import numpy as np
import six
import json
import copy
from common import util
from common import tf_util


class ModelCreatorABC(abc.ABC):
    def __init__(self, model_name):
        self.model_name = model_name
        self.probabilities = None

    @abc.abstractmethod
    def get_model_conf(self):
        pass

    @classmethod
    def get_name_to_features(cls):
        seq_length = 128
        max_predictions_per_seq = 15
        # name_to_features = {
        #     "input_ids": tf.io.FixedLenFeature([seq_length], tf.int64),
        #     "input_mask": tf.io.FixedLenFeature([seq_length], tf.int64),
        #     "segment_ids": tf.io.FixedLenFeature([seq_length], tf.int64),
        #     "label_ids": tf.io.FixedLenFeature([], tf.int64)
        # }
        # name_to_features = {
        #     "input_ids": tf.io.FixedLenFeature([seq_length], tf.int64),
        #     "input_mask": tf.io.FixedLenFeature([seq_length], tf.int64),
        #     "sentence_ids": tf.io.FixedLenFeature([seq_length], tf.int64),
        #     "tts_dist": tf.io.FixedLenFeature([seq_length], tf.float32),
        #     "segment_ids": tf.io.FixedLenFeature([seq_length], tf.int64),
        #     "label": tf.io.FixedLenFeature([], tf.int64),
        #     "sample_id": tf.io.FixedLenFeature([], tf.int64)
        # }
        name_to_features = {
            "input_ids": tf.io.FixedLenFeature([seq_length], tf.int64),
            "input_mask": tf.io.FixedLenFeature([seq_length], tf.int64),
            "segment_ids": tf.io.FixedLenFeature([seq_length], tf.int64),

            "masked_lm_positions": tf.io.FixedLenFeature([max_predictions_per_seq], tf.int64),
            "masked_lm_ids": tf.io.FixedLenFeature([max_predictions_per_seq], tf.int64),
            "masked_lm_weights": tf.io.FixedLenFeature([max_predictions_per_seq], tf.float32),
            "next_sentence_labels": tf.io.FixedLenFeature([], tf.int64),

            "sentence_ids": tf.io.FixedLenFeature([seq_length], tf.int64),
            "tts_dist": tf.io.FixedLenFeature([seq_length], tf.float32),
            "sample_id": tf.io.FixedLenFeature([], tf.int64),
            "order_id": tf.io.FixedLenFeature([], tf.string),
            "code_links": tf.io.FixedLenFeature([], tf.string)
        }
        return name_to_features

    @classmethod
    def get_assignment_map_from_checkpoint(cls, tvars, init_checkpoint, verbose=False):
        """Compute the union of the current variables and checkpoint variables."""
        assignment_map = collections.OrderedDict()
        trainable_variable_in_ckpt = {}
        trainable_variable_not_in_ckpt = {}
        ckpt_variables_in_trainable = {}
        ckpt_variables_not_in_trainable = {}

        name_to_variable = collections.OrderedDict()
        for var in tvars:
            name = var.name
            m = re.match("^(.*):\\d+$", name)
            if m is not None:
                name = m.group(1)
            name_to_variable[name] = var
        try:
            init_vars = tf.train.list_variables(init_checkpoint)
        except:
            init_vars = []
        for (name, shape) in init_vars:
            if name not in name_to_variable:
                ckpt_variables_not_in_trainable[name] = 1
                ckpt_variables_not_in_trainable[name + ":0"] = 1
                continue
            assignment_map[name] = name
            ckpt_variables_in_trainable[name] = shape
            ckpt_variables_in_trainable[name + ":0"] = shape

        trainable_variables_log_s = "[get_assignment_map_from_checkpoint] trainable_variables\n"
        for var in tvars:
            name = var.name
            m = re.match("^(.*):\\d+$", name)
            if m is not None:
                name = m.group(1)
            if name in ckpt_variables_in_trainable:
                trainable_variable_in_ckpt[name] = var.shape
                trainable_variables_log_s += "*** INIT_FROM_CKPT_TRAINABLE_VAR *** name = {}, shape = {}\n".format(name, str(var.shape))
            else:
                trainable_variable_not_in_ckpt[name] = var.shape
                trainable_variables_log_s += " name = {}, shape = {}\n".format(name, str(var.shape))

        assert len(trainable_variable_in_ckpt) == len(ckpt_variables_in_trainable) / 2
        tf.logging.info("""[get_assignment_map_from_checkpoint] trainable_variables: {}, init_checkpoint: {}
        trainable_variable_in_ckpt: {}, trainable_variable_not_in_ckpt: {}
        ckpt_variables_in_trainable: {}, ckpt_variables_not_in_trainable: {}
        """.format(len(tvars), init_checkpoint,
                   len(trainable_variable_in_ckpt), len(trainable_variable_not_in_ckpt),
                   len(ckpt_variables_in_trainable) / 2, len(ckpt_variables_not_in_trainable) / 2))

        if verbose:
            tf.logging.info(trainable_variables_log_s)
            ckpt_variables_not_in_trainable_log_s = "[get_assignment_map_from_checkpoint] ckpt_variables_not_in_trainable:\n"
            for name in ckpt_variables_not_in_trainable:
                if ":0" in name:
                    continue
                ckpt_variables_not_in_trainable_log_s += "name = {}, shape = {} \n".format(name, str(ckpt_variables_not_in_trainable[name]))
            tf.logging.info(ckpt_variables_not_in_trainable_log_s)

        return (assignment_map, trainable_variable_in_ckpt, trainable_variable_not_in_ckpt, ckpt_variables_in_trainable, ckpt_variables_not_in_trainable)

    @abc.abstractmethod
    def create_model(self, features, labels, is_training):
        input_ids = features["input_ids"]
        input_mask = features["input_mask"]
        segment_ids = features["segment_ids"]
        labels = features["label"]
        num_labels = 2

        output_layer = tf.cast(input_ids, tf.float32)

        hidden_size = output_layer.shape[-1].value
        output_weights = tf.get_variable("output_weights", [num_labels, hidden_size], initializer=tf.truncated_normal_initializer(stddev=0.02))

        output_bias = tf.get_variable(
            "output_bias", [num_labels], initializer=tf.zeros_initializer())

        with tf.variable_scope("loss"):
            if is_training:
                # I.e., 0.1 dropout
                output_layer = tf.nn.dropout(output_layer, keep_prob=0.9)

            logits = tf.matmul(output_layer, output_weights, transpose_b=True)
            logits = tf.nn.bias_add(logits, output_bias)
            probabilities = tf.nn.softmax(logits, axis=-1)
            self.probabilities = probabilities
            log_probs = tf.nn.log_softmax(logits, axis=-1)

            one_hot_labels = tf.one_hot(labels, depth=num_labels, dtype=tf.float32)

            batch_loss = -tf.reduce_sum(one_hot_labels * log_probs, axis=-1)
            batch_mean_loss = tf.reduce_mean(batch_loss)

            return (logits, probabilities, batch_mean_loss, batch_loss)

    @staticmethod
    def _decay_warmup_lr(global_step, init_lr, num_decay_steps, end_learning_rate, decay_pow, num_warmup_steps):
        learning_rate = tf.constant(value=init_lr, shape=[], dtype=tf.float32)

        # Implements linear decay of the learning rate.
        learning_rate = tf.train.polynomial_decay(
            learning_rate,
            global_step,
            num_decay_steps,
            end_learning_rate=end_learning_rate,
            power=decay_pow,
            cycle=False)

        # Implements linear warmup. I.e., if global_step < num_warmup_steps, the
        # learning rate will be `global_step/num_warmup_steps * init_lr`.
        if num_warmup_steps:
            global_steps_int = tf.cast(global_step, tf.int32)
            warmup_steps_int = tf.constant(num_warmup_steps, dtype=tf.int32)

            global_steps_float = tf.cast(global_steps_int, tf.float32)
            warmup_steps_float = tf.cast(warmup_steps_int, tf.float32)

            warmup_percent_done = global_steps_float / warmup_steps_float
            warmup_learning_rate = init_lr * warmup_percent_done

            is_warmup = tf.cast(global_steps_int < warmup_steps_int, tf.float32)
            learning_rate = ((1.0 - is_warmup) * learning_rate + is_warmup * warmup_learning_rate)
        return learning_rate

    @classmethod
    def create_train_op(cls, loss, init_lr, num_decay_steps, end_learning_rate, decay_pow, num_warmup_steps, use_tpu=False):
        """Creates an optimizer training op."""
        global_step = tf.train.get_or_create_global_step()
        learning_rate = cls._decay_warmup_lr(global_step, init_lr, num_decay_steps, end_learning_rate, decay_pow, num_warmup_steps)

        # It is recommended that you use this optimizer for fine tuning, since this
        # is how the models was trained (note that the Adam m/v variables are NOT
        # loaded from init_checkpoint.)
        optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate, epsilon=1e-6)

        if use_tpu:
            optimizer = tf.contrib.tpu.CrossShardOptimizer(optimizer)

        tvars = tf.trainable_variables()
        grads = tf.gradients(loss, tvars)

        # This is how the models was pre-trained.
        (grads, _) = tf.clip_by_global_norm(grads, clip_norm=1.0)

        train_op = optimizer.apply_gradients(
            zip(grads, tvars), global_step=global_step)

        # Normally the global step update is done inside of `apply_gradients`.
        # However, `AdamWeightDecayOptimizer` doesn't do this. But if you use
        # a different optimizer, you should probably take this line out.
        # new_global_step = global_step + 1
        # train_op = tf.group(train_op, [global_step.assign(new_global_step)])
        return train_op

    @classmethod
    def create_metric_ops(cls, batch_loss, labels, logits, is_real_example=1):
        predictions = tf.argmax(logits, axis=-1, output_type=tf.int32)
        accuracy = tf.metrics.accuracy(labels=labels, predictions=predictions, weights=is_real_example)
        loss = tf.metrics.mean(values=batch_loss, weights=is_real_example)
        return {
            "eval_accuracy": accuracy,
            "eval_loss": loss,
        }

    def create_predict_ops(self):
        predictions = {"probabilities": self.probabilities}
        return predictions

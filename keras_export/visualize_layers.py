#!/usr/bin/env python3
"""Generate images maximally activating filters/neurons of a given model.
"""

import base64
import datetime
import json
import struct
import sys

import numpy as np

from scipy.misc import imsave

from keras.models import load_model
from keras import backend as K

# based on: https://blog.keras.io/how-convolutional-neural-networks-see-the-world.html
__author__ = "Francois Chollet, Tobias Hermann"
__copyright__ = "Copyright 2016 Francois Chollet, 2017 Tobias Hermann"
__license__ = "MIT"
__maintainer__ = "Tobias Hermann, https://github.com/Dobiasd/frugally-deep"
__email__ = "editgym@gmail.com"


def deprocess_image(x):
    # normalize tensor: center on 0., ensure std is 0.1
    x -= x.mean()
    x /= (x.std() + K.epsilon())
    x *= 0.1

    # clip to [0, 1]
    x += 0.5
    x = np.clip(x, 0, 1)

    # convert to RGB array
    x *= 255
    if K.image_data_format() == 'channels_first':
        x = x.transpose((1, 2, 0))
    x = np.clip(x, 0, 255).astype('uint8')
    return x


def normalize(x):
    # utility function to normalize a tensor by its L2 norm
    return x / (K.sqrt(K.mean(K.square(x))) + K.epsilon())


def process_conv_2d_layer(layer, input_img):
    filter_cnt = layer.get_weights()[0].shape[-1]
    print('Processing layer {} with {} filters'.format(layer.name, filter_cnt))
    img_width, img_height, img_chans = input_img.shape[1:4]
    kept_filters = []
    for filter_index in range(filter_cnt):
        # we only scan through the first 200 filters,
        # but there are actually 512 of them
        print('Processing filter %d' % filter_index)

        # we build a loss function that maximizes the activation
        # of the nth filter of the layer considered
        loss = K.mean(layer.output[:, :, :, filter_index])

        # we compute the gradient of the input picture wrt this loss
        grads = K.gradients(loss, input_img)[0]

        # normalization trick: we normalize the gradient
        grads = normalize(grads)

        # this function returns the loss and grads given the input picture
        iterate = K.function([input_img], [loss, grads])

        # step size for gradient ascent
        step = 1.

        # we start from a gray image with some random noise
        input_img_data = np.random.random((1, img_width, img_height, img_chans))
        input_img_data = (input_img_data - 0.5) * 20 + 128

        # we run gradient ascent for 20 steps
        for i in range(20):
            loss_value, grads_value = iterate([input_img_data])
            input_img_data += grads_value * step

            #print('Current loss value:', loss_value)
            if loss_value <= 0.:
                # some filters get stuck to 0, we can skip them
                print('Skipping filter {}, loss {}'.format(
                    filter_index, loss_value))
                break

        # decode the resulting input image
        if loss_value > 0:
            img = deprocess_image(input_img_data[0])
            kept_filters.append((img, loss_value))

    return kept_filters


def is_ascii(some_string):
    """Check if a string only contains ascii characters"""
    try:
        some_string.encode('ascii')
    except UnicodeEncodeError:
        return False
    else:
        return True


def process_layers(model, out_dir):
    """Visualize all filters of all layers"""
    process_layer_functions = {
        #'Conv1D': process_conv_1d_layer,
        'Conv2D': process_conv_2d_layer,
        #'Conv2DTranspose': process_conv_2d_transpose_layer,
        #'SeparableConv2D': process_separable_conv_2d_layer,
        #'Dense': process_dense_layer
    }
    result = {}
    layers = model.layers
    for layer in layers:
        layer_type = type(layer).__name__
        if layer_type in ['Model', 'Sequential']:
            result = process_layers(layer)
        else:
            process_func = process_layer_functions.get(layer_type, None)
            name = layer.name
            assert is_ascii(name)
            if process_func:
                images_with_loss = process_func(layer, model.input)
                for i, (image, loss) in enumerate(images_with_loss):
                    date_time_str = datetime.datetime.now().strftime("%Y-%m-%d_%H_%M_%S_%f")
                    image = np.squeeze(image)
                    imsave('{}/{}_{}_{}_{}.png'.format(
                        out_dir, date_time_str, name, i, loss), image)
    return result


def convert_sequential_to_model(model):
    """Convert a sequential model to the underlying functional format"""
    if type(model).__name__ == 'Sequential':
        name = model.name
        inbound_nodes = model.inbound_nodes
        model = model.model
        model.name = name
        model.inbound_nodes = inbound_nodes
    assert model.input_layers
    assert model.layers
    for i in range(len(model.layers)):
        if type(model.layers[i]).__name__ in ['Model', 'Sequential']:
            model.layers[i] = convert_sequential_to_model(model.layers[i])
    return model


def main():
    """Convert any Keras model to the frugally-deep model format."""

    usage = 'usage: [Keras model in HDF5 format] [image output directory]'
    if len(sys.argv) != 3:
        print(usage)
        sys.exit(1)
    else:
        assert K.backend() == "tensorflow"
        assert K.floatx() == "float32"
        assert K.image_data_format() == 'channels_last'

        in_path = sys.argv[1]
        out_dir = sys.argv[2]
        print('loading {}'.format(in_path))
        K.set_learning_phase(1)
        model = load_model(in_path)
        model = convert_sequential_to_model(model)
        process_layers(model, out_dir)


if __name__ == "__main__":
    main()
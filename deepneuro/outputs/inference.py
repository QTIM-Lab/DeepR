
import os

from deepneuro.outputs.output import Output
from deepneuro.utilities.util import add_parameter, replace_suffix
from deepneuro.utilities.conversion import save_numpy_2_nifti

import numpy as np

class ModelInference(Output):

    def load(self, kwargs):

        """ Parameters
            ----------
            depth : int, optional
                Specified the layers deep the proposed U-Net should go.
                Layer depth is symmetric on both upsampling and downsampling
                arms.
            max_filter: int, optional
                Specifies the number of filters at the bottom level of the U-Net.

        """


        add_parameter(self, kwargs, 'ground_truth', None)

        add_parameter(self, kwargs, 'save_to_file', True)
        add_parameter(self, kwargs, 'output_types', ['probability', 'binary_label'])
        add_parameter(self, kwargs, 'binarize_probability', .5)

        add_parameter(self, kwargs, 'channels_first', False)
        add_parameter(self, kwargs, 'input_channels', None)

        if 'channels_dim' in kwargs:
            self.channels_dim = kwargs.get('channels_dim')
        elif self.channels_first:
            self.channels_dim = 1
        else:
            self.channels_dim = -1

        self.return_objects = []

    def execute(self):

        # Create output directory. If not provided, output into original patient folder.
        if self.output_directory is not None:
            if not os.path.exists(self.output_directory):
                os.makedirs(self.output_directory)

        print 'CURRENT CASE: ', self.case

        if self.case is None:

            # At present, this only works for one input, one output patch networks.
            data_generator = self.data_collection.data_generator()

            input_data = next(data_generator)
            while input_data is not None:

                self.process_case(input_data)

                input_data = next(data_generator)
        else:
            self.process_case(self.data_collection.get_data(self.case))

        return self.return_objects

    def process_case(self, input_data):

        # A little bit strange to access casename this way. Maybe make it an optional
        # return of the generator.
        casename = self.data_collection.data_groups[self.inputs[0]].base_casename
        affine = self.data_collection.data_groups[self.inputs[0]].base_affine

        if self.data_collection.augmentations != []:
            augmentation_string = self.data_collection.data_groups[self.inputs[0]].augmentation_strings[-1]
        else:
            augmentation_string = ''

        if self.output_directory is None:
            output_directory = casename
        else:
            output_directory = self.output_directory

        output_filepath = os.path.join(output_directory, replace_suffix(self.output_filename, '', augmentation_string))

        # If prediction already exists, skip it. Useful if process is interrupted.
        if os.path.exists(output_filepath) and not self.replace_existing:
            return

        # If an image is being repatched, its output shape is not certain. We attempt to infer it from
        # the input data. This is wonky. Move this to PatchInference, maybe.

        if self.channels_first:
            input_data = np.swapaxes(input_data[0], 1, -1)
        else:
            # Temporary code. In the future, make sure code works with multiple and specific inputs.
            input_data = input_data[0]

        if self.input_channels is not None:
            input_data = np.take(input_data, self.input_channels, self.channels_dim)

        self.output_shape = [1] + list(self.model.model.layers[-1].output_shape)[1:] # Weird
        for i in xrange(len(self.patch_dimensions)):
            self.output_shape[self.output_patch_dimensions[i]] = input_data.shape[self.patch_dimensions[i]]

        output_data = self.predict(input_data)

        # Will fail for time-data.
        if self.channels_first:
            output_data = np.swapaxes(output_data, 1, -1)

        if self.save_to_file:
            self.return_objects.append(self.save_prediction(output_data, output_filepath, input_affine=affine, ground_truth=input_data[0]))
        else:
            self.return_objects.append(output_data)

    def predict(self, input_data, model, batch_size):

        # Vanilla prediction case is obivously not fleshed out.
        prediction = model.predict(input_data)

        return prediction

    def save_prediction(self, input_data, output_filepath, input_affine=None, ground_truth=None, stack_outputs=False):

        """ This is a temporary function borrowed from qtim_ChallengePipeline. In the future, will be rewritten in a more
            DeepNeuro way..
        """

        output_shape = input_data.shape
        input_data = np.squeeze(input_data)

        return_filenames = []

        # If there is only one channel, only save one file.
        if output_shape[-1] == 1:

            if 'probability' in self.output_types:
                return_filenames += [save_numpy_2_nifti(input_data, input_affine, output_filepath=replace_suffix(output_filepath, input_suffix='', output_suffix='-probability'))]

            if 'binary_label' in self.output_types:
                binary_data = self.threshold_binarize(threshold=self.binarize_probability, input_data=input_data)
                return_filenames += [save_numpy_2_nifti(binary_data, input_affine, output_filepath=replace_suffix(output_filepath, input_suffix='', output_suffix='-label'))]

        else:
            pass
            # Return to case for multiple outputs.

        return_filenames = replace_suffix(output_filepath, input_suffix='', output_suffix='-label')

        return return_filenames

    def threshold_binarize(self, input_data, threshold):

        return (input_data > threshold).astype(float)

    def calculate_prediction_dice(self, label_volume_1, label_volume_2):

        im1 = np.asarray(label_volume_1).astype(np.bool)
        im2 = np.asarray(label_volume_2).astype(np.bool)

        if im1.shape != im2.shape:
            raise ValueError("Shape mismatch: im1 and im2 must have the same shape.")

        im_sum = im1.sum() + im2.sum()
        if im_sum == 0:
            return empty_score

        # Compute Dice coefficient
        intersection = np.logical_and(im1, im2)

        return 2. * intersection.sum() / im_sum

class ModelPatchesInference(ModelInference):

    def load(self, kwargs):

        """ Parameters
            ----------
            depth : int, optional
                Specified the layers deep the proposed U-Net should go.
                Layer depth is symmetric on both upsampling and downsampling
                arms.
            max_filter: int, optional
                Specifies the number of filters at the bottom level of the U-Net.

        """

        super(ModelPatchesInference, self).load(kwargs)

        if 'patch_overlaps' in kwargs:
            self.patch_overlaps = kwargs.get('patch_overlaps')
        else:
            self.patch_overlaps = 1

        if 'patch_dimensions' in kwargs:
            self.patch_dimensions = kwargs.get('patch_dimensions')
        else:
            # TODO: Set better defaults.
            if self.channels_first:
                self.patch_dimensions = [-3,-2,-1]
            else:
                self.patch_dimensions = [-4,-3,-2]

        # A little tricky to not refer to previous paramter as input_patch_dimensions
        if 'output_patch_dimensions' in kwargs:
            self.output_patch_dimensions = kwargs.get('output_patch_dimensions')
        else:
            self.output_patch_dimensions = self.patch_dimensions

        if 'output_patch_shape' in kwargs:
            self.output_patch_shape = kwargs.get('output_patch_shape')
        else:
            self.output_patch_shape = None

        if 'pad_borders' in kwargs:
            self.pad_borders = kwargs.get('pad_borders')
        else:
            self.pad_borders = True

        if 'check_empty_patch' in kwargs:
            self.check_empty_patch = kwargs.get('check_empty_patch')
        else:
            self.check_empty_patch = True

    def execute(self):

        # Determine patch shape. Currently only extends to spatial patching.
        # This leading dims business has got to have a better solution..
        self.input_patch_shape = self.model.model.layers[0].input_shape
        if self.output_patch_shape is None:
            self.output_patch_shape = self.model.model.layers[-1].output_shape

        super(ModelPatchesInference, self).execute()

        return self.return_objects


    def predict(self, input_data):

        repatched_image = np.zeros(self.output_shape)

        repetition_offsets = [np.linspace(0, self.input_patch_shape[axis]-1, self.patch_overlaps, dtype=int) for axis in self.patch_dimensions]

        if self.pad_borders:
            # I use this three-line loop construciton a lot. Is there a more sensible way?
            input_pad_dimensions = [(0,0)] * input_data.ndim
            output_pad_dimensions = [(0,0)] * repatched_image.ndim
            for idx, dim in enumerate(self.patch_dimensions):
                # Might not work for odd-shaped patches; check.
                input_pad_dimensions[dim] = (int(self.input_patch_shape[dim]/2), int(self.input_patch_shape[dim]/2))
            for idx, dim in enumerate(self.output_patch_dimensions):
                output_pad_dimensions[dim] = (int(self.input_patch_shape[dim]/2), int(self.input_patch_shape[dim]/2))

            input_data = self.pad_data(input_data, input_pad_dimensions)
            repatched_image = self.pad_data(repatched_image, output_pad_dimensions)

        corner_data_dims = [input_data.shape[axis] for axis in self.patch_dimensions]
        corner_patch_dims = [self.output_patch_shape[axis] for axis in self.patch_dimensions]

        all_corners = np.indices(corner_data_dims)

        # There must be a better way to round up to an integer..
        possible_corners_slice = [slice(None)] + [slice(self.input_patch_shape[dim]/2, -self.input_patch_shape[dim]/2, None) for dim in self.patch_dimensions]
        all_corners = all_corners[possible_corners_slice]

        for rep_idx in xrange(self.patch_overlaps):

            if self.verbose:
                print 'Patch prediction repetition level ..', rep_idx

            corners_grid_shape = [slice(None)]
            for dim in xrange(all_corners.ndim - 1):
                corners_grid_shape += [slice(repetition_offsets[dim][rep_idx], corner_data_dims[dim], corner_patch_dims[dim])]

            corners_list = all_corners[corners_grid_shape]
            corners_list = np.reshape(corners_list, (corners_list.shape[0], -1)).T

            if self.check_empty_patch:
                corners_list = self.remove_empty_patches(input_data, corners_list)

            for corner_list_idx in xrange(0, corners_list.shape[0], self.batch_size):

                corner_batch = corners_list[corner_list_idx:corner_list_idx+self.batch_size]
                input_patches = self.grab_patch(input_data, corner_batch)

                prediction = self.model.model.predict(input_patches)
                
                self.insert_patch(repatched_image, prediction, corner_batch)

            if rep_idx == 0:
                output_data = np.copy(repatched_image)
            else:
                output_data = output_data + (1.0 / (rep_idx)) * (repatched_image - output_data) # Running Average

        if self.pad_borders:

            output_slice = [slice(None)] * output_data.ndim # Weird
            for idx, dim in enumerate(self.output_patch_dimensions):
                # Might not work for odd-shaped patches; check.
                output_slice[dim] = slice(self.input_patch_shape[dim]/2, -self.input_patch_shape[dim]/2, 1)
            output_data = output_data[output_slice]

        return output_data

    def pad_data(self, data, pad_dimensions):

        # Maybe more effecient than np.pad? Created for testing a different purpose.

        for idx, width in enumerate(pad_dimensions):
            pad_block_1, pad_block_2 = list(data.shape), list(data.shape)
            pad_block_1[idx] = width[0]
            pad_block_2[idx] = width[1]
            data = np.concatenate((np.zeros(pad_block_1), data, np.zeros(pad_block_2)), axis=idx)

        return data

    def remove_empty_patches(self, input_data, corners_list):

        corner_selections = []

        for corner_idx, corner in enumerate(corners_list):
            output_slice = [slice(None)] * input_data.ndim # Weird
            for idx, dim in enumerate(self.patch_dimensions):
                output_slice[dim] = slice(corner[idx] - self.input_patch_shape[dim]/2, corner[idx] + self.input_patch_shape[dim]/2, 1)

            corner_selections += [np.any(input_data[output_slice])]

        return corners_list[corner_selections]

    def grab_patch(self, input_data, corner_list):

        """ Given a corner coordinate, a patch_shape, and some input_data, returns a patch or array of patches.
        """

        output_patches_shape = (corner_list.shape[0], ) + self.input_patch_shape[1:]
        output_patches = np.zeros((output_patches_shape))

        for corner_idx, corner in enumerate(corner_list):
            output_slice = [slice(None)] * input_data.ndim # Weird
            for idx, dim in enumerate(self.patch_dimensions):
                output_slice[dim] = slice(corner[idx] - self.input_patch_shape[dim]/2, corner[idx] + self.input_patch_shape[dim]/2, 1)

            output_patches[corner_idx, ...] = input_data[output_slice]

        return output_patches

    def insert_patch(self, input_data, patches, corner_list):

        # Some ineffeciencies in the function. TODO: come back and rewrite.

        for corner_idx, corner in enumerate(corner_list):
            insert_slice = [slice(None)] * input_data.ndim # Weird
            for idx, dim in enumerate(self.output_patch_dimensions):
                # Might not work for odd-shaped patches; check.
                insert_slice[dim] = slice(corner[idx] - self.output_patch_shape[dim]/2, corner[idx] + self.output_patch_shape[dim]/2, 1)

            insert_patch = patches[corner_idx, ...]
            if not np.array_equal(np.take(self.output_patch_shape, self.output_patch_dimensions), np.take(self.input_patch_shape, self.patch_dimensions)): # Necessary if statement?
                patch_slice = [slice(None)] * insert_patch.ndim # Weird
                for idx, dim in enumerate(self.output_patch_dimensions):
                    # Might not work for odd-shaped patches; check.
                    patch_slice[dim] = slice((self.input_patch_shape[dim] - self.output_patch_shape[dim])/2, -(self.input_patch_shape[dim] - self.output_patch_shape[dim])/2, 1)

                insert_patch = insert_patch[patch_slice]

            input_data[insert_slice] = insert_patch

        return input_data
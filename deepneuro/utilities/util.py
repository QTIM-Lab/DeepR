import math
import os

def round_up(x, y):
    return int(math.ceil(float(x) / float(y)))


def add_parameter(class_object, kwargs, parameter, default=None):
    if parameter in kwargs:
        setattr(class_object, parameter, kwargs.get(parameter))
    else:
        setattr(class_object, parameter, default)

def nifti_splitext(input_filepath):

    """ os.path.splitext splits a filename into the part before the LAST
        period and the part after the LAST period. This will screw one up
        if working with, say, .nii.gz files, which should be split at the
        FIRST period. This function performs an alternate version of splitext
        which does just that.

        TODO: Make work if someone includes a period in a folder name (ugh).

        Parameters
        ----------
        input_filepath: str
            The filepath to split.

        Returns
        -------
        split_filepath: list of str
            A two-item list, split at the first period in the filepath.

    """

    split_filepath = str.split(input_filepath, '.')

    if len(split_filepath) <= 1:
        return split_filepath
    else:
        return [split_filepath[0], '.' + '.'.join(split_filepath[1:])]

def replace_suffix(input_filepath, input_suffix, output_suffix, suffix_delimiter=None):

    """ Replaces an input_suffix in a filename with an output_suffix. Can be used
        to generate or remove suffixes by leaving one or the other option blank.

        TODO: Make suffixes accept regexes. Can likely replace suffix_delimiter after this.
        TODO: Decide whether suffixes should extend across multiple directory levels.

        Parameters
        ----------
        input_filepath: str
            The filename to be transformed.
        input_suffix: str
            The suffix to be replaced
        output_suffix: str
            The suffix to replace with.
        suffix_delimiter: str
            Optional, overrides input_suffix. Replaces whatever 
            comes after suffix_delimiter with output_suffix.

        Returns
        -------
        output_filepath: str
            The transformed filename
    """

    if os.path.isdir(input_filepath):
        split_filename = [input_filepath, '']
    else:
        split_filename = nifti_splitext(input_filepath)

    if suffix_delimiter is not None:
        input_suffix = str.split(split_filename[0], suffix_delimiter)[-1]

    if input_suffix not in os.path.basename(input_filepath):
        print 'ERROR!', input_suffix, 'not in input_filepath.'
        return []

    else:
        if input_suffix == '':
            prefix = split_filename[0]
        else:
            prefix = input_suffix.join(str.split(split_filename[0], input_suffix)[0:-1])
        prefix = prefix + output_suffix
        output_filepath = prefix + split_filename[1]
        return output_filepath
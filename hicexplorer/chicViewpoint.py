import argparse
import sys
import numpy as np
import hicmatrix.HiCMatrix as hm
from hicexplorer import utilities
from .lib import Viewpoint
from hicexplorer._version import __version__
from scipy.stats import zscore
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os
from multiprocessing import Process, Queue
import time
import math
import logging
log = logging.getLogger(__name__)


def parse_arguments(args=None):
    parser = argparse.ArgumentParser(add_help=False,
                                     description='Plots the number of interactions around a given reference point in a region.')

    parserRequired = parser.add_argument_group('Required arguments')

    parserRequired.add_argument('--matrices', '-m',
                                help='path of the Hi-C matrices to plot',
                                required=True,
                                nargs='+')

    parserRequired.add_argument('--range',
                                help='Defines the region upstream and downstream of a reference point which should be included. '
                                'Format is --region upstream downstream',
                                required=True,
                                type=int,
                                nargs=2)

    parserRequired.add_argument('--referencePoints', '-rp', help='Reference point file. Needs to be in the format: \'chr 100\' for a '
                                'single reference point or \'chr 100 200\' for a reference region and per line one reference point',
                                required=True)
    parserRequired.add_argument('--backgroundModelFile', '-bmf',
                                help='path to the background file which is necessary to compute the rbz-score',
                                required=True)
    parserOpt = parser.add_argument_group('Optional arguments')
    parserOpt.add_argument('--threads',
                           help='Number of threads. Using the python multiprocessing module. ',
                           required=False,
                           default=4,
                           type=int
                           )
    parserOpt.add_argument('--averageContactBin',
                           help='Average the contacts of n bins, written to last column.',
                           type=int,
                           default=0)
    parserOpt.add_argument('--fixateRange', '-fs',
                           help='Fixate range of backgroundmodel starting at distance x. E.g. all values greater 500kb are set to the value of the 500kb bin.',
                           required=False,
                           default=500000,
                           type=int
                           )
    parserOpt.add_argument("--help", "-h", action="help", help="show this help message and exit")

    parserOpt.add_argument('--version', action='version',
                           version='%(prog)s {}'.format(__version__))
    return parser


def adjustViewpointData(pViewpointObj, pData, pBackground, pSEM, pReferencePoint, pRegionStart, pRegionEnd):
    data_viewpoint = {}
    data_background = {}
    data_sem = {}
    view_point_start, _ = pViewpointObj.getReferencePointAsMatrixIndices(pReferencePoint)
    view_point_range_start, view_point_range_end = \
        pViewpointObj.getViewpointRangeAsMatrixIndices(pReferencePoint[0], pRegionStart, pRegionEnd)

    for i, data in zip(range(view_point_range_start, view_point_range_end, 1), pData):
        relative_position = i - view_point_start
        data_viewpoint[relative_position] = data
            # relative_positions.add(relative_position)
    for i, data in zip(range(view_point_range_start, view_point_range_end, 1), pBackground):
        relative_position = i - view_point_start
        # if relative_position in data_background:
        #     log.debug('relative_position 2nd time: {}'.format(relative_position))
        #     log.debug('relative_position 2nd time: daata {}'.format(data))
        #     log.debug('relative_position 2nd time: data 1st time {}'.format(data_background[relative_position]))

        data_background[relative_position] = data
    
    for i, data in zip(range(view_point_range_start, view_point_range_end, 1), pSEM):
        relative_position = i - view_point_start
        data_sem[relative_position] = data
    
    for i in data_background:
        if i in data_viewpoint:
            continue
        else:
            data_viewpoint[i] = 0
            # log.debug('key unique: {}'.format(i))

    # log.debug()sssss
    # log.debug('len(data_viewpoint) {}'.format(len(data_viewpoint)))
    # log.debug('len(data_background) {}'.format(len(data_background)))
    # log.debug('len(data_sem) {}\n\n'.format(len(data_sem)))

    data = np.fromiter(data_viewpoint.values(), dtype=np.float32)
    background = np.fromiter(data_background.values(), dtype=np.float32)
    sem = np.fromiter(data_sem.values(), dtype=np.float32)

    # log.debug('data_viewpoint {}'.format(data_viewpoint))
    # log.debug('data_background {}'.format(data_background))
    # log.debug('data_sem {}'.format(data_sem))

    return data, background, sem

    # exit()

def compute_viewpoint(pViewpointObj, pArgs, pQueue, pReferencePoints, pGeneList, pMatrix, pBackgroundModel):

    for i, referencePoint in enumerate(pReferencePoints):
        # range of viewpoint with reference point in the middle in genomic units
        # get fixateRange for relative interaction computation denominator
        region_start_fixed, region_end_fixed, range_fixed = pViewpointObj.calculateViewpointRange(referencePoint, (pArgs.fixateRange, pArgs.fixateRange))

        # log.debug(' {} {} {} {}'.format(referencePoint, referencePoint[0], region_start_(fixed, region_end_fixed))
        intermediate_viewpoint = pViewpointObj.computeViewpoint(referencePoint, referencePoint[0], region_start_fixed, region_end_fixed)
        # log.debug('intermediate, on fixate range {}'.format(intermediate_viewpoint[:15]))
        # print('fixated range viewpoint: ' + str())
        denominator_relative_interactions = np.sum(pViewpointObj.computeViewpoint(referencePoint, referencePoint[0], region_start_fixed, region_end_fixed))

        # viewpoint data uses full range
        region_start, region_end, _range = pViewpointObj.calculateViewpointRange(referencePoint, pArgs.range)

        data_list = pViewpointObj.computeViewpoint(referencePoint, referencePoint[0], region_start, region_end)
        # log.debug('on full data: {}'.format(data_list[:15]))
        # print('range viewpoint: '+ str(data_list[:10]))

        # background uses fixed range, handles fixate range implicitly by same range used in background computation
        _backgroundModelData, _backgroundModelSEM = pViewpointObj.interactionBackgroundData(pBackgroundModel, _range)
        # log.debug(' after interactionBackgroundDaa len(data_list) {}'.format(len(data_list)))

        # log.debug('data_list {}'.format(data_list[:15]))

        if len(data_list) != len(_backgroundModelData):

            data_list, _backgroundModelData, _backgroundModelSEM = adjustViewpointData(pViewpointObj, data_list, _backgroundModelData, _backgroundModelSEM, referencePoint, region_start, region_end)

        
        if pArgs.averageContactBin > 0:
            data_list = pViewpointObj.smoothInteractionValues(data_list, pArgs.averageContactBin)
        
        data_list_raw = np.copy(data_list)

        data_list = pViewpointObj.computeRelativeValues(data_list, denominator_relative_interactions)

        rbz_score_data = pViewpointObj.rbz_score(data_list, _backgroundModelData, _backgroundModelSEM)

        # add values if range is larger than fixate range

        region_start_range, region_end_range, _ = pViewpointObj.calculateViewpointRange(referencePoint, (pArgs.range[0], pArgs.range[1]))

        interaction_data = pViewpointObj.createInteractionFileData(referencePoint, referencePoint[0],
                                                                    region_start_range, region_end_range, data_list, data_list_raw,
                                                                    pGeneList[i])

        referencePointString = '_'.join(str(j) for j in referencePoint)

        region_start_in_units = utilities.in_units(region_start)
        region_end_in_units = utilities.in_units(region_end)
        denominator_relative_interactions_str = 'Sum of interactions in fixate range: ' 
        denominator_relative_interactions_str += str(denominator_relative_interactions)
        header_information = '\t'.join([pMatrix, referencePointString, str(region_start_in_units), str(region_end_in_units), pGeneList[i], denominator_relative_interactions_str])
        header_information += '\n# ChrViewpoint\tStart\tEnd\tGene\tChrInteraction\tStart\tEnd\tRelative position\tRelative Interactions\trbz-score\tRaw\n#'
        matrix_name = '.'.join(pMatrix.split('.')[:-1])
        matrix_name = '_'.join([matrix_name, referencePointString, pGeneList[i]])
    
        pViewpointObj.writeInteractionFile(matrix_name, interaction_data, header_information, rbz_score_data)

    pQueue.put(['Done'])
    return

def main(args=None):
    args = parse_arguments().parse_args(args)

    viewpointObj = Viewpoint()

    referencePoints, gene_list = viewpointObj.readReferencePointFile(args.referencePoints)
    referencePointsPerThread = len(referencePoints) // args.threads
    queue = [None] * args.threads
    process = [None] * args.threads
    background_model = viewpointObj.readBackgroundDataFile(args.backgroundModelFile, args.range)
    for matrix in args.matrices:
        hic_ma = hm.hiCMatrix(matrix)
        viewpointObj.hicMatrix = hic_ma

        all_data_collected = False

        # log.debug('len(referencePoints) {}'.format(referencePoints))

        # compute_viewpoint(
        #         pViewpointObj = viewpointObj,
        #         pArgs = args,
        #         pQueue = None,
        #         pReferencePoints = referencePoints,
        #         pGeneList = gene_list,
        #         pMatrix = matrix,
        #         pBackgroundModel = background_model)

        for i in range(args.threads):
            
            if i < args.threads - 1:
                referencePointsThread = referencePoints[i*referencePointsPerThread:(i+1)*referencePointsPerThread]
                geneListThread = gene_list[i*referencePointsPerThread:(i+1)*referencePointsPerThread]
            else:
                referencePointsThread = referencePoints[i*referencePointsPerThread:]
                geneListThread = gene_list[i*referencePointsPerThread:]

            queue[i] = Queue()
            process[i] = Process(target=compute_viewpoint, kwargs=dict(
                pViewpointObj = viewpointObj,
                pArgs = args,
                pQueue =queue[i],
                pReferencePoints = referencePointsThread,
                pGeneList = geneListThread,
                pMatrix = matrix,
                pBackgroundModel = background_model
                )
            )

            process[i].start()

        while not all_data_collected:
            for i in range(args.threads):
                if queue[i] is not None and not queue[i].empty():
                    _ = queue[i].get()
                    process[i].join()
                    process[i].terminate()
                    process[i] = None
                #     log.debug('Thread {} DONE'.format(i))
                # log.debug('Thread {} WAIT'.format(i))
                
            all_data_collected = True
            
            for i in range(args.threads):
                if process[i] is not None:
                    all_data_collected = False
            time.sleep(1)


            # log.debug('referencePoint {}'.format(referencePoint))
            # region_start, region_end, _range = viewpointObj.calculateViewpointRange(referencePoint, args.range)

            # data_list = viewpointObj.computeViewpoint(referencePoint, referencePoint[0], region_start, region_end)
            # if args.averageContactBin > 0:
            #     data_list = viewpointObj.smoothInteractionValues(data_list, args.averageContactBin)
            
            
            # bin_start_viewpoint, bin_end_viewpoint = viewpointObj.hicMatrix.getRegionBinRange(referencePoint[0], region_start, region_end)
            # # log.debug('region_start {}'.format(foo))
            # # log.debug('region_end {}'.format(region_end))

            # # log.debug('len(data_list) {}'.format(len(data_list)))
            # data_list = data_list[bin_start_viewpoint:bin_end_viewpoint]
            # # log.debug('len(data_list) {}'.format(len(data_list)))

            # data_list_raw = np.copy(data_list)

            # data_list = viewpointObj.computeRelativeValues(data_list)

            # if args.backgroundModelFile:
            #     _background_model = viewpointObj.readBackgroundDataFile(args.backgroundModelFile)
            #     _backgroundModelData, _backgroundModelSEM = viewpointObj.interactionBackgroundData(_background_model, _range)
            #     rbz_score_data = viewpointObj.rbz_score(data_list, _backgroundModelData, _backgroundModelSEM)

            # interaction_data = viewpointObj.createInteractionFileData(referencePoint, referencePoint[0],
            #                                                           region_start, region_end, data_list, data_list_raw,
            #                                                           gene_list[i])

            # referencePointString = '_'.join(str(j) for j in referencePoint)

            # region_start_in_units = utilities.in_units(region_start)
            # region_end_in_units = utilities.in_units(region_end)

            # header_information = '\t'.join([matrix, referencePointString, str(region_start_in_units), str(region_end_in_units), gene_list[i]])
            # header_information += '\n# ChrViewpoint\tStart\tEnd\tChrInteraction\tStart\tEnd\tRelative position\tRelative Interactions\trbz-score\tRaw\n#'
            # matrix_name = '.'.join(matrix.split('.')[:-1])
            # matrix_name = '_'.join([matrix_name, referencePointString, gene_list[i]])
            # viewpointObj.writeInteractionFile(matrix_name, interaction_data, header_information, rbz_score_data)
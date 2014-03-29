import numpy as np
import pandas as pd
import logging

log = logging.getLogger(__name__)
from ..matrices import LinkBlock
from ..matrices import DiagBlock
from ..matrices import CostMatrix

from ..cost_function import AbstractLinkCostFunction
from ..cost_function import AbstractDiagCostFunction

# from ..cost_function import BrownianCostFunction
# from ..cost_function import DiagCostFunction

from . import AbstractSolver


class GapCloseSolver(AbstractSolver):
    """

    Parameters
    ----------
    trajs : pandas.DataFrame
    cost_functions : list of list
    """
    def __init__(self, trajs, cost_functions,
                 maximum_gap, coords=['x', 'y', 'z']):
        
        super().__init__(trajs)

        self.coords = coords

        self.trajs.check_trajs_df_structure(index=['t_stamp', 'label'],
                                            columns=['t'] + coords)

        self.link_cf = cost_functions['link']
        self.check_cost_function_type(self.link_cf, AbstractLinkCostFunction)

        self.birth_cf = cost_functions['birth']
        self.check_cost_function_type(self.birth_cf, AbstractDiagCostFunction)

        self.death_cf = cost_functions['death']
        self.check_cost_function_type(self.death_cf, AbstractDiagCostFunction)

        self.maximum_gap = maximum_gap

    @property
    def blocks_structure(self):
        return [[self.link_block.mat, self.death_block.mat],
                [self.birth_block.mat, None]]


    def track(self):

        labels = self.trajs.labels
        idxs_in, idxs_out = self._get_candidates()
        self.link_cf.context['trajs'] = self.trajs
        self.link_cf.context['idxs_in'] = idxs_in
        self.link_cf.context['idxs_out'] = idxs_out
        
        if not len(idxs_in):
            log.info('No gap needs closing here...')
            return self.trajs
        old_labels = self.trajs.index.get_level_values('label').values
        self.trajs['new_label'] = old_labels.astype(np.float)
        self.link_block = LinkBlock(labels, labels, self.link_cf)

        # ''' TFA: For track segment ends and starts, the alternative cost (b and d in Fig. 1c) had to be
        # comparable in magnitude to the costs of potential assignments, making the rejection
        # of gap closing, merging and splitting an accessible alternative. At the same time, the
        # alternative cost had to be at the higher end of the range of potential assignment costs,
        # so that the algorithm did not fail to close gaps and capture merge and split events. We
        # performed empirical tests of the sensitivity of tracking results to variations in the
        # alternative cost. We found that in a range 80th – 100th percentile of all potential
        # assignment costs the outcome of gap closing, merging and splitting varied negligibly
        # (data not shown). We attribute this robustness to the fact that track initiations and
        # terminations competed globally, in space and time, with all other potential
        # assignments. Thus, the alternative cost was taken as the 90th percentile.'''

        percentile = 99
        link_costs = np.ma.masked_invalid(self.link_block.mat).compressed()
        cost = np.percentile(link_costs, percentile)
        self.birth_cf.context['cost'] = cost
        self.death_cf.context['cost'] = cost
        self.birth_block = DiagBlock(labels, self.birth_cf)
        self.death_block = DiagBlock(labels, self.death_cf)
        self.cm = CostMatrix(self.blocks_structure)
        self.cm.solve()
        self.assign()
        return self.trajs
        
        
    def _get_candidates(self):
        """
        
        """
        max_gap = self.maximum_gap
        labels = self.trajs.labels
        bounds = np.array([(idxs[0][0], idxs[-1][0]) for idxs
                           in self.trajs.segment_idxs.values()])
        start_times = bounds[:, 0]
        stop_times = bounds[:, 1]
        ss_in, ss_out = np.meshgrid(labels, labels)
        gaps_size = start_times[ss_out] - stop_times[ss_in]
        matches = np.argwhere((gaps_size > 0) * (gaps_size < max_gap))
        if not matches.shape[0]:
            return [], []
        matches_in = matches[:, 0]
        matches_out = matches[:, 1]
        
        in_idxs = [(in_time, in_lbl) for (in_time, in_lbl)
                   in zip(start_times[matches_in],
                          self.trajs.labels[matches_in])]
        #pos_in = self.trajs.loc[in_idxs]
        out_idxs = [(out_time, out_lbl) for (out_time, out_lbl)
                    in zip(start_times[matches_out],
                           self.trajs.labels[matches_out])]
        #pos_out = self.trajs.loc[out_idxs]
        return in_idxs, out_idxs

    def assign(self):
        """
        """
        row_shapes, col_shapes = self.cm.get_shapes()
        old_labels = self.trajs.index.get_level_values(level='label').values
        new_labels = old_labels.copy()
        unique_old = self.trajs.labels.copy() #np.unique(old_labels)
        unique_new = self.trajs.labels.copy() #np.unique(new_labels)

        last_in_link = row_shapes[0]
        last_out_link = col_shapes[0]

        for idx_out, idx_in in enumerate(self.cm.out_links[:last_out_link]):
            if idx_in >= last_in_link:
                ## no merge
                unique_new[idx_out] = unique_new.max() + 1
            else:
                # do merge
                new_label = unique_new[idx_in]
                unique_new[idx_out] = new_label
                
        for old, new in zip(unique_old, unique_new):
            new_labels[old_labels == old] = new

        self.relabel_trajs(new_labels)
        return self.trajs

            
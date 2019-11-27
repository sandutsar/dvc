import logging
import os

import colorama

from . import locked
from dvc.exceptions import RecursiveAddingWhileUsingFilename
from dvc.progress import Tqdm
from dvc.repo.scm_context import scm_context
from dvc.stage import Stage
from dvc.utils import LARGE_DIR_SIZE

logger = logging.getLogger(__name__)


@locked
@scm_context
def add(repo, targets, recursive=False, no_commit=False, fname=None):
    if recursive and fname:
        raise RecursiveAddingWhileUsingFilename()

    if isinstance(targets, str):
        targets = [targets]

    stages_list = []
    num_targets = len(targets)
    with Tqdm(total=num_targets, desc="Add", unit="file", leave=True) as pbar:
        if num_targets == 1:
            # clear unneeded top-level progress bar for single target
            pbar.bar_format = "Adding..."
            pbar.refresh()
        for target in targets:
            sub_targets = _find_all_targets(repo, target, recursive)
            pbar.total += len(sub_targets) - 1

            if os.path.isdir(target) and len(sub_targets) > LARGE_DIR_SIZE:
                logger.warning(
                    "You are adding a large directory '{target}' recursively,"
                    " consider tracking it as a whole instead.\n"
                    "{purple}HINT:{nc} Remove the generated DVC-file and then"
                    " run `{cyan}dvc add {target}{nc}`".format(
                        purple=colorama.Fore.MAGENTA,
                        cyan=colorama.Fore.CYAN,
                        nc=colorama.Style.RESET_ALL,
                        target=target,
                    )
                )

            stages = _create_stages(repo, sub_targets, fname, pbar=pbar)

            repo.check_modified_graph(stages)

            for stage in Tqdm(stages, desc="Processing", unit="file"):
                stage.save()

                if not no_commit:
                    stage.commit()

                stage.dump()

            stages_list += stages

        if num_targets == 1:
            pbar.bar_format = pbar.BAR_FMT_DEFAULT

    return stages_list


def _find_all_targets(repo, target, recursive):
    if os.path.isdir(target) and recursive:
        return [
            fname
            for fname in Tqdm(
                repo.tree.walk_files(target),
                desc="Recursing " + target,
                bar_format=Tqdm.BAR_FMT_NOTOTAL,
                unit="file",
            )
            if not repo.is_dvc_internal(fname)
            if not Stage.is_stage_file(fname)
            if not repo.scm.belongs_to_scm(fname)
            if not repo.scm.is_tracked(fname)
        ]
    return [target]


def _create_stages(repo, targets, fname, pbar=None):
    stages = []

    for out in Tqdm(
        targets,
        desc="Creating stages",
        disable=len(targets) < LARGE_DIR_SIZE,
        unit="file",
    ):
        stage = Stage.create(repo, outs=[out], add=True, fname=fname)

        if not stage:
            if pbar is not None:
                pbar.total -= 1
            continue

        stages.append(stage)
        if pbar is not None:
            pbar.update_desc(out)

    return stages

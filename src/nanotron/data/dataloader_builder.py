from torch.utils.data import DataLoader

import nanotron.distributed as dist
from nanotron import logging
from nanotron.data.dataloader import (
    DataCollatorForCLM,
    DataCollatorForCLMWithPositionIds,
    get_dataloader_worker_init,
)
from nanotron.data.samplers import (
    EmptyInfiniteDataset,
    get_sampler,
)
from nanotron.parallel import ParallelContext

logger = logging.get_logger(__name__)


def build_nanoset_dataloader(
    dataset,
    sequence_length: int,
    parallel_context: ParallelContext,
    input_pp_rank: int,
    output_pp_rank: int,
    micro_batch_size: int,
    dataloader_num_workers: int,
    consumed_train_samples: int = 0,
    dataloader_drop_last: bool = True,
    dataloader_pin_memory: bool = True,
    use_position_ids: bool = True,
) -> DataLoader:

    # Case of ranks not requiring data. We give them a dummy dataset, then the collator will do his job
    if dist.get_rank(parallel_context.pp_pg) not in [input_pp_rank, output_pp_rank]:
        dataset_length = len(dataset)
        dataset = EmptyInfiniteDataset(length=dataset_length)
        # No need to spawn a lot of workers, we can just use main
        dataloader_num_workers = 0

    if use_position_ids:
        data_collator = DataCollatorForCLMWithPositionIds(
            sequence_length=sequence_length,
            input_pp_rank=input_pp_rank,
            output_pp_rank=output_pp_rank,
            parallel_context=parallel_context,
        )
    else:
        data_collator = DataCollatorForCLM(
            sequence_length=sequence_length,
            input_pp_rank=input_pp_rank,
            output_pp_rank=output_pp_rank,
            parallel_context=parallel_context,
        )

    # Compute size and rank of dataloader workers
    dp_ranks_size = parallel_context.dp_pg.size()
    dp_rank = parallel_context.dp_pg.rank()

    sampler = get_sampler(
        train_dataset=dataset,
        dl_ranks_size=dp_ranks_size,
        dl_rank=dp_rank,
        drop_last=dataloader_drop_last,
        consumed_train_samples=consumed_train_samples,
        shuffle=False,
    )

    return DataLoader(
        dataset,
        batch_size=micro_batch_size,
        sampler=sampler,
        collate_fn=data_collator,
        drop_last=dataloader_drop_last,
        num_workers=dataloader_num_workers,
        pin_memory=dataloader_pin_memory,
        worker_init_fn=get_dataloader_worker_init(dp_rank=dp_rank),
        pin_memory_device="cuda",
        persistent_workers=True if dataloader_num_workers > 0 else False,
        prefetch_factor=dataloader_num_workers if dataloader_num_workers > 0 else None,
    )

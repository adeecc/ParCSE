from typing import Optional

from torch.utils.data import DataLoader

import pytorch_lightning as pl

from datasets import load_dataset
from transformers import AutoTokenizer

from paraphrasegen.constants import NUM_WORKERS, PATH_DATASETS, PATH_BASE_MODELS


class CRLDataModule(pl.LightningDataModule):
    text_field_map = {
        "mrpc": ["sentence1", "sentence2"],
        "qqp": ["question1", "question2"],
        "paws": ["sentence1", "sentence2"],
    }

    dataset_args_map = {
        "mrpc": ["glue", "mrpc"],
        "qqp": [
            "glue",
            "qqp",
        ],  # Using glue/qqp rather than quora to maintain uniform format
        "paws": [
            "paws",
            "labeled_final",
        ],  # We use just the labeled_final DataField for now
    }

    columns = [
        "anchor_input_ids",
        "anchor_attention_mask",
        "target_input_ids",
        "target_attention_mask",
        "labels",
    ]

    def __init__(
        self,
        model_name_or_path: str,
        task_name: str = "qqp",
        max_seq_length: int = 32,
        padding: str = "max_length",
        batch_size: int = 32,
    ):
        super().__init__()

        self.model_name_or_path = model_name_or_path
        self.task_name = task_name
        self.max_seq_length = max_seq_length
        self.padding = padding
        self.batch_size = batch_size

        self.text_fields = self.text_field_map[task_name]
        self.dataset_args = self.dataset_args_map[task_name]
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name_or_path, use_fast=True, cache_dir=PATH_BASE_MODELS
        )

    def prepare_data(self) -> None:
        load_dataset(*self.dataset_args, cache_dir=PATH_DATASETS)

    def setup(self, stage: Optional[str] = None) -> None:
        self.dataset = load_dataset(*self.dataset_args, cache_dir=PATH_DATASETS)

        self.dataset["train"] = self.dataset["train"].filter(
            lambda el: el["label"] == 1
        )
        # self.dataset["validation"] = self.dataset["validation"].filter(
        #     lambda el: el["label"] == 1
        # )

        self.dataset = self.dataset.map(
            self.convert_to_features,
            batched=True,
            remove_columns=(
                [
                    "label",
                ]
                + self.text_fields
            ),
            num_proc=NUM_WORKERS,
        )

        self.dataset.set_format(type="torch", columns=self.columns)

    def train_dataloader(self):
        return DataLoader(
            self.dataset["train"],
            batch_size=self.batch_size,
            num_workers=NUM_WORKERS,
            drop_last=True,
        )

    def val_dataloader(self):
        return DataLoader(
            self.dataset["validation"],
            batch_size=self.batch_size,
            num_workers=NUM_WORKERS,
            drop_last=True,
        )

    def test_dataloader(self):
        return DataLoader(
            self.dataset["test"],
            batch_size=self.batch_size,
            num_workers=NUM_WORKERS,
            drop_last=True,
        )

    def convert_to_features(self, example_batch, indices=None):
        features = {}
        tokenized_anchor = self.tokenizer(
            example_batch[self.text_fields[0]],
            max_length=self.max_seq_length,
            padding=self.padding,
            truncation=True,
        )

        tokenized_target = self.tokenizer(
            example_batch[self.text_fields[1]],
            max_length=self.max_seq_length,
            padding=self.padding,
            truncation=True,
        )

        for key, value in tokenized_anchor.items():
            features[f"anchor_{key}"] = value

        for key, value in tokenized_target.items():
            features[f"target_{key}"] = value

        features["labels"] = example_batch["label"]

        return features


if __name__ == "__main__":
    dm = CRLDataModule("distilbert-base-uncased")
    dm.prepare_data()
    dm.setup("fit")

    print(next(iter(dm.train_dataloader())))

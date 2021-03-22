#!/usr/bin/env python
#
# Author: Thamme Gowda [tg (at) isi (dot) edu]
# Created: 3/12/21

import copy
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, List, Tuple, Union
from rtg import log
from rtg.exp import TranslationExperiment
from rtg.registry import register_model
from rtg.utils import get_my_args
from rtg.module import Model
from rtg.module.trainer import SteppedTrainer
from rtg.module.tfmnmt import (Encoder, EncoderLayer, MultiHeadedAttention, PositionwiseFeedForward,
                               PositionalEncoding, Embeddings, SimpleLossFunction)



class SequenceClassifier(nn.Module):
    scores = {
        'logits': lambda x, dim=None: x,
        'softmax': F.softmax,
        'log_softmax': F.log_softmax,
        'sigmoid': lambda x, dim=None: x.sigmoid(),
        'embedding': None,
    }

    def __init__(self, d_model: int, n_classes: int, attn: MultiHeadedAttention):
        super().__init__()
        self.d_model = d_model
        self.n_classes = n_classes
        # cls_repr vector is used to compute sentence representation from token representation
        # How: weighted average over tokens aka attention
        self.cls_repr = nn.Parameter(torch.zeros(d_model))
        self.attn = attn
        self.proj = nn.Linear(d_model, n_classes)

    def forward(self, src, src_mask, score='logits'):
        score = score or 'logits'
        B, T, D = src.size()  # [Batch, Time, Dim]
        assert D == self.d_model
        assert score in self.scores, f'"score", Given={score}, known={list(self.scores.keys())}'
        # Args: Query, Key, Value, Mask
        query = self.cls_repr.view(1, 1, D).repeat(B,1,1)
        cls_repr = self.attn(query, src, src, src_mask)
        cls_repr = cls_repr.squeeze()  # [B, D]
        if score == 'embedding':
            return cls_repr
        cls_repr = self.proj(cls_repr)
        return self.scores[score](cls_repr, dim=-1)


class ClassificationExperiment(TranslationExperiment):
    """Treat source as source sequence, target as class"""
    pass
    """
    train
    """
    def pre_process(self, args=None, force=False):
        args = args or self.config.get('prep')
        is_shared = args.get('shared')
        assert not is_shared, 'Shared vocab not supported for Classification.' \
                              ' Please set prep.shared=False'
        # skip TranslationExperiment, go to its parent BaseExperiment pre_process
        super(TranslationExperiment, self).pre_process(args=args, force=force)

        if self.has_prepared() and not force:
            log.warning("Already prepared")
            return

        # check if files are parallel
        self.check_line_count('validation', args['valid_src'], args['valid_tgt'])
        if 'spark' in self.config:
            log.warning(f"Spark backend detected: line count on training data is skipped")
        else:
            log.warning(f"Going to count lines. If this is a big dataset, it will take long time")
            self.check_line_count('training', args['train_src'], args['train_tgt'])

        xt_args = dict(no_split_toks=args.get('no_split_toks'),
                       char_coverage=args.get('char_coverage', 0))

        src_corpus = [args[key] for key in ['train_src', 'mono_src'] if args.get(key)]
        max_src_size = args.get('max_src_types', args.get('max_types', None))
        assert max_src_size, 'prep.max_src_types or prep.max_types must be defined'
        self.src_field = self._make_vocab("src", self._src_field_file, args['pieces'],
                                          vocab_size=max_src_size, corpus=src_corpus, **xt_args)

        # target vocabulary; class names. treat each line as a word
        tgt_corpus = [args[key] for key in ['train_tgt'] if args.get(key)]
        self.tgt_field = self._make_vocab("src", self._tgt_field_file, 'class', corpus=tgt_corpus)

        train_file = self.train_db

        self._pre_process_parallel('train_src', 'train_tgt', out_file=train_file, args=args,
                                   line_check=False)
        self._pre_process_parallel('valid_src', 'valid_tgt', out_file=self.valid_file, args=args,
                                   line_check=False)

        if args.get("finetune_src") or args.get("finetune_tgt"):
            self._pre_process_parallel('finetune_src', 'finetune_tgt', self.finetune_file)
        self._prepared_flag.touch()

        """
        # get samples from validation set
        n_samples = args.get('num_samples', 10)
        space_tokr = lambda line: line.strip().split()
        val_raw_recs = TSVData.read_raw_parallel_recs(
            args['valid_src'], args['valid_tgt'], args['truncate'], args['src_len'],
            args['tgt_len'], src_tokenizer=space_tokr, tgt_tokenizer=space_tokr)
        val_raw_recs = list(val_raw_recs)
        random.shuffle(val_raw_recs)
        samples = val_raw_recs[:n_samples]
        TSVData.write_parallel_recs(samples, self.samples_file)
        """


@register_model
class TransformerClassifier(Model):

    model_type = 'tfmcls'
    experiment_type = ClassificationExperiment

    EncoderFactory = Encoder
    EncoderLayerFactory = EncoderLayer
    ClassifierFactory = SequenceClassifier

    def __init__(self, encoder: Encoder, src_embed, classifier):
        super().__init__()
        self.encoder: Encoder = encoder
        self.src_embed = src_embed
        self.classifier = classifier

    def encode(self, src, src_mask):
        return self.encoder(self.src_embed(src), src_mask)

    def forward(self, src, tgt, src_mask, score=None):
        "Take in and process masked src and target sequences."
        enc_outs = self.encode(src, src_mask)
        return self.classifier(enc_outs, src_mask, score=score)

    @classmethod
    def make_model(cls, src_vocab: int, tgt_vocab: int, enc_layers=6, hid_size=512, ff_size=2048,
                   n_heads=8, attn_bias=True, attn_dropout=0.1, dropout=0.1, activation='relu',
                   exp: ClassificationExperiment = None):
        "Helper: Construct a model from hyper parameters."

        # get all args for reconstruction at a later phase
        args = get_my_args(exclusions=['cls', 'exp'])
        assert activation in {'relu', 'elu', 'gelu'}
        assert enc_layers > 0, "Zero encoder layers!"

        log.info(f"Make model, Args={args}")
        c = copy.deepcopy
        attn = MultiHeadedAttention(n_heads, hid_size, dropout=attn_dropout, bias=attn_bias)
        ff = PositionwiseFeedForward(hid_size, ff_size, dropout, activation=activation)
        encoder = cls.EncoderFactory(cls.EncoderLayerFactory(hid_size, c(attn), c(ff), dropout),
                                                            enc_layers)
        src_emb = nn.Sequential(Embeddings(hid_size, src_vocab),
                                PositionalEncoding(hid_size, dropout))
        classifier = cls.ClassifierFactory(d_model=hid_size, n_classes=tgt_vocab, attn=c(attn))

        model = cls(encoder, src_emb, classifier)

        model.init_params()
        return model, args

    @classmethod
    def make_trainer(cls, *args, **kwargs):
        return ClassifierTrainer(*args, **kwargs)


class ClassifierTrainer(SteppedTrainer):

    def __init__(self, exp: ClassificationExperiment,
                 model: Optional[TransformerClassifier] = None,
                 optim: str = 'ADAM',
                 model_factory=TransformerClassifier.make_model,
                 **optim_args):
        super().__init__(exp, model, model_factory=model_factory, optim=optim, **optim_args)
        trainer_args = self.exp.config.get('trainer', {}).get('init_args', {})
        chunk_size = trainer_args.get('chunk_size', -1)
        if chunk_size > 0:
            log.warning("chunk_size not supported for this setup; it is ignored")
        self.grad_accum_interval = trainer_args.get('grad_accum', 1)
        assert self.grad_accum_interval > 0

        if self.n_gpus > 1:  # Multi GPU mode
            raise Exception(f"Please use: python -m rtg.distrib.launch -G {self.n_gpus} \n "
                            f" or set single GPU by: export CUDA_VISIBLE_DEVICES=0 ")

        generator = self.core_model.generator
        self.loss_func = SimpleLossFunction(generator=generator, criterion=self.criterion,
                                                opt=self.opt)


if __name__ == '__main__':
    args = dict(src_vocab=8000, n_classes=3, enc_layers=2, hid_size=128, ff_size=256, n_heads=2)
    model, args_2 = TransformerClassifier.make_model(**args)
    # if you are running this in pycharm, please set Working Dir=<rtg repo base dir> for run config
    dir = 'experiments/sample-exp'
    from rtg.exp import TranslationExperiment as Experiment
    exp = Experiment(work_dir=dir, read_only=True)
    model.train()
    data = exp.get_train_data(batch_size=256, steps=100)
    for batch in data:
        x_mask = (batch.x_seqs != batch.pad_val).unsqueeze(1)
        ys = torch.randint(low=0, high=args['n_classes'], size=(len(batch), 1))
        res = model(src=batch.x_seqs, tgt=ys, src_mask=x_mask)
        print(res)
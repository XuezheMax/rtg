# RTG

RTG is a Neural Machine Translation toolkit based on pytorch.
RTG stands for Reader-Translator-Generator when it is noun, and read-translate-generate when it is a verb.
This toolkit is meant for MT/NLG/NLU research.
<small>NOTE: It has no relation to the [regular tree grammar](https://en.wikipedia.org/wiki/Regular_tree_grammar))</small>

### Includes  :
+ Flexible Pre-processing : [sentencepiece](https://github.com/google/sentencepiece) is under the hood
+ Translation Modeling:
  + [Transformer aka Tensor2Tensor or "Attention is all you need"](https://arxiv.org/abs/1706.03762)
  + [RNN based Encoder-Decoder](https://papers.nips.cc/paper/5346-sequence-to-sequence-learning-with-neural-networks.pdf) with [Attention](https://nlp.stanford.edu/pubs/emnlp15_attn.pdf)
+ Language Modeling:
  + RNN
  + Transformer


### Goals:
+ Easy and interpretable code (for those who read code as much as papers)
  + Should be easy to adapt to new settings (the long term goal)
+ Reproducible experiments, based on config files and experiment directory
  + YAML is a friendly format


### TODO :
 + Multi GPU Parallelism (Work in progress)


### Setup

```bash
git clone git@github.com:thammegowda/rtg.git
cd rtg                # go to the code
export PYTHONPATH=$PWD  # Add directory to PYTHONPATH
```

# Usage
This repo is actively under development so whatever I write in README is getting outdated soon.
Refer to `scripts/rtg-pipeline.sh` and bash script and `examples/pipeline.conf.yml` file

TODO: Write tutorial
```bash
$ mkdir 001-tfm
$ cp examples/pipeline.conf.yml 001-tfm/conf.yml
$ scripts/rtg-pipeline.sh -d 001-tfm
```

---------
### Authors:
[See Here](https://github.com/thammegowda/rtg/graphs/contributors)


### Credits / Thanks
+ OpenNMT and the Harvard NLP team for [Annotated transformer](http://nlp.seas.harvard.edu/2018/04/03/attention.html), I learned a lot from their work
+ [My team at USC ISI](https://www.isi.edu/research_groups/nlg/people) for everything else



# GPFormer: Multi-Horizon Glucose Prediction with Deep Domain Generalization

Leveraging meta-learning for domain generalization and quantile loss, we propose GPFormer, a Transformer-based zero-shot learning method designed for multi-horizon glucose prediction for up to 120 minutes.

## Paper Information
- **Authors**: Taiyu Zhu, Ioannis Afentakis, Kezhi Li, Ryan Armiger, Neil Hill, Nick Oliver, Pantelis Georgiou
- **Affiliations**: University of Oxford, Imperial College London, University College London
- **Preprint**: TBA

## Dataset Preparation
| Dataset   | Access Link | Instructions |
|-----------|-------------|--------------|
| REPLACE-BG| [Access from JCHR](https://public.jaeb.org/datasets/diabetes) | Accept the Data Use Agreement (DUA) |
| OhioT1DM  | [Access from Ohio University](http://smarthealth.cs.ohio.edu/OhioT1DM-dataset.html) | Accept the DUA and submit an application form |
| ABC4D     | [Access from Corresponding Authors](https://www.liebertpub.com/doi/abs/10.1089/dia.2022.0504) | Email: [ken.li@ucl.ac.uk](mailto:ken.li@ucl.ac.uk) |
| GVAS      | [Access from Corresponding Authors](https://diabetesjournals.org/diabetes/article/72/Supplement_1/933-P/150011/933-P-Glycemic-Level-and-Glycemic-Variability-in) | Email: [ken.li@ucl.ac.uk](mailto:ken.li@ucl.ac.uk) |

After downloading the data, create PyTorch dataloaders using a sliding window approach for look-back sequences (six hours) and prediction sequences (two hours).

## Usage
To train and test the model, run:
```
bash scripts/run.sh
```
## Directory Hierarchy
```
|—— .gitignore
|—— args_generator.py
|—— layers
|    |—— Embed.py
|    |—— SelfAttention_Family.py
|    |—— Transformer_EncDec.py
|    |—— utils.py
|    |—— __init__.py
|—— main.py
|—— models
|    |—— GPFormer.py
|    |—— __init__.py
|—— README_.md
|—— saved_models
|    |—— GPFormer.pth
|—— scripts
|    |—— run.sh
|—— utils
|    |—— data.py
|    |—— masking.py
|    |—— meter.py
|    |—— timefeatures.py
|    |—— __init__.py
```
## Code Details
### Tested Platform
- software
  ```
  Python: 3.9.12
  PyTorch: 1.11.0
  ```
- hardware
  ```
  CPU: Intel(R) Core(TM) i7-7700K
  GPU: Nvidia 1080Ti (11GB)
  ```


## Acknowledgments & References
This work was inspired by the folloing papers
- [Informer](https://cdn.aaai.org/ojs/17325/17325-13-20819-1-2-20210518.pdf)
- [Meta-Learning for Domain Generalization](https://cdn.aaai.org/ojs/11596/11596-13-15124-1-2-20201228.pdf)

We extend our gratitude to the following GitHub repositories for their valuable  code and contributions:
- [TSlib](https://github.com/thuml/Time-Series-Library)
- [Transfer-Learning-Library](https://github.com/thuml/Transfer-Learning-Library)
  
## License
BSD 3-Clause License

Copyright (c) 2024, Imperial College London.
All rights reserved.

## Citing
Please use the following BibTeX entry.
```
TBA
```

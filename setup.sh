pip install opencv-python-headless==4.1.2.30 -U -q

python -m pix2tex.dataset.dataset -i dataset/data/images_train -e dataset/data/im2latex_formulas.norm.lst -o dataset/data/train.pkl
python -m pix2tex.dataset.dataset -i dataset/data/images_val -e dataset/data/im2latex_formulas.norm.lst -o dataset/data/val.pkl
python -m pix2tex.dataset.dataset -i dataset/data/images_test -e dataset/data/im2latex_formulas.norm.lst -o dataset/data/test.pkl
python -m pix2tex.dataset.dataset --equations dataset/data/im2latex_formulas.norm.lst --vocab-size 1000 --out dataset/data/tokenizer_small.json

"""
Crea larva_1clase/: una copia del dataset larva/ con las 6 clases (larva_1 ... larva_6)
unidas en una sola clase 'larva'. El dataset original no se modifica.
Las imagenes se enlazan (hard link), asi que no ocupan espacio extra.
"""
import os
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ORIGEN = os.path.join(BASE_DIR, 'larva')
DESTINO = os.path.join(BASE_DIR, 'larva_1clase')


def enlazar_o_copiar(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


if __name__ == '__main__':
    if os.path.exists(DESTINO):
        shutil.rmtree(DESTINO)

    for split in ('train', 'valid', 'test'):
        dir_img = os.path.join(ORIGEN, split, 'images')
        dir_lbl = os.path.join(ORIGEN, split, 'labels')
        if not os.path.isdir(dir_img):
            continue
        out_img = os.path.join(DESTINO, split, 'images')
        out_lbl = os.path.join(DESTINO, split, 'labels')
        os.makedirs(out_img)
        os.makedirs(out_lbl)

        for nombre in os.listdir(dir_img):
            enlazar_o_copiar(os.path.join(dir_img, nombre), os.path.join(out_img, nombre))

        n_objetos = 0
        for nombre in os.listdir(dir_lbl):
            with open(os.path.join(dir_lbl, nombre)) as f:
                lineas = [l.split() for l in f.read().splitlines() if l.strip()]
            # Todas las clases pasan a ser la clase 0
            lineas = ['0 ' + ' '.join(p[1:]) for p in lineas]
            n_objetos += len(lineas)
            with open(os.path.join(out_lbl, nombre), 'w') as f:
                f.write('\n'.join(lineas) + '\n')

        print(f"{split}: {len(os.listdir(out_img))} imagenes, {n_objetos} larvas")

    with open(os.path.join(DESTINO, 'data.yaml'), 'w') as f:
        f.write(f"path: {DESTINO}\n"
                "train: train/images\n"
                "val: valid/images\n"
                "test: test/images\n\n"
                "nc: 1\n"
                "names: ['larva']\n")
    print(f"Dataset listo en {DESTINO}")

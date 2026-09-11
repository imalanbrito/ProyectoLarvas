from ultralytics import YOLO
if __name__=='__main__': YOLO('yolov8n-seg.pt').train(data='/Users/alan/Desktop/LUMACAD/ProyectoLarvas/data.yaml', epochs=100, device='mps')
"""Train an image classifier for one MediSmart imaging module (transfer learning, MobileNetV2).

NOT RUN in the environment this project was generated in (no TensorFlow / datasets there) - treat as a starting point.

Dataset layout (one folder per class, names must match backend/app/services/imaging.py labels):
    data/chest-xray/train/{normal,pneumonia,tuberculosis}/*.jpg   (+ data/chest-xray/val/...)

Suggested public datasets: Kaggle "Chest X-Ray Images (Pneumonia)", "Brain Tumor MRI Dataset",
HAM10000 (skin lesions), APTOS 2019 (diabetic retinopathy), MURA (bone). Check each licence/terms.

Usage:
    pip install tensorflow
    python ml/train_image_classifier.py --kind chest-xray --data data/chest-xray --epochs 8
The model is saved to backend/models/<kind>.keras and loaded automatically by the API.
"""
import argparse
import os

import tensorflow as tf

p = argparse.ArgumentParser()
p.add_argument("--kind", required=True)
p.add_argument("--data", required=True)
p.add_argument("--epochs", type=int, default=8)
p.add_argument("--size", type=int, default=224)
a = p.parse_args()

train = tf.keras.utils.image_dataset_from_directory(os.path.join(a.data, "train"), image_size=(a.size, a.size), batch_size=32, label_mode="categorical")
val = tf.keras.utils.image_dataset_from_directory(os.path.join(a.data, "val"), image_size=(a.size, a.size), batch_size=32, label_mode="categorical")
classes = train.class_names
print("classes (must match the labels in imaging.py, in this alphabetical order):", classes)

base = tf.keras.applications.MobileNetV2(input_shape=(a.size, a.size, 3), include_top=False, weights="imagenet")
base.trainable = False
inp = tf.keras.Input((a.size, a.size, 3))
x = tf.keras.layers.RandomFlip("horizontal")(inp)
x = tf.keras.layers.RandomRotation(0.05)(x)
x = tf.keras.applications.mobilenet_v2.preprocess_input(x)  # NOTE: the API sends raw 0-255 pixels, so preprocessing lives inside the model
x = base(x, training=False)
x = tf.keras.layers.GlobalAveragePooling2D()(x)
x = tf.keras.layers.Dropout(0.3)(x)
out = tf.keras.layers.Dense(len(classes), activation="softmax")(x)
model = tf.keras.Model(inp, out)
model.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="categorical_crossentropy", metrics=["accuracy", tf.keras.metrics.AUC(name="auc")])
model.fit(train, validation_data=val, epochs=a.epochs)

os.makedirs("backend/models", exist_ok=True)
model.save(f"backend/models/{a.kind}.keras")
print("saved backend/models/%s.keras  - evaluate on a held-out test set (sensitivity/specificity) before any demo claims." % a.kind)

from ml_models.breast_cancer_inference import predict_breast_cancer
from ml_models.pneumonia_inference import predict_pneumonia

result = predict_breast_cancer("case-inflammatory-breast-cancer-fig1.jpg")
#result = predict_pneumonia("case-inflammatory-breast-cancer-fig1.jpg")
print(result)


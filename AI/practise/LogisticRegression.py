import numpy
import pandas
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report

# 读取数据
dataSet=pandas.read_csv('E:\桌面\\牛马找车拉\\深度学习\\源码\\逻辑回归实战---乳腺癌检测\\breast_cancer_data.csv')
# print(dataSet.head)

# 提取x
X=dataSet.iloc[:,:-1]
# print(x)

# 提取数据标签y
Y=dataSet['target']
# print(y)

# 划分数据集
x_train,x_test,y_train,y_test=train_test_split(X,Y,test_size=0.2)

# 数据归一化
scaler=MinMaxScaler(feature_range=(0,1))
x_train=scaler.fit_transform(x_train)
x_test=scaler.transform(x_test)
# print(x_train)
# print(x_test) 

# 逻辑回归建模
lr=LogisticRegression()
lr.fit(x_train,y_train)

# 打印模型参数
# print('w:',lr.coef_)
# print('b:',lr.intercept_)    

# 利用模型进行推理测试
pre_result=lr.predict(x_test)
# print('预测结果:',pre_result)

# 打印预测结果的概率
pre_result_proba=lr.predict_proba(x_test)
# print('预测结果的概率:',pre_result_proba)

# 获取恶行肿瘤概率
pre_list=pre_result_proba[:,1]
# print('恶性肿瘤概率:',pre_list)

# 设置阈值
threshold=0.2

# 设置保存结果的列表
result=[]
result_name=[]

for i in range(len(pre_list)):
    if pre_list[i]>threshold:
        result.append(1)
        result_name.append('恶性肿瘤')
    else:
        result.append(0)
        result_name.append('良性肿瘤')
        
# print('预测结果:',result)
# print('预测结果名称:',result_name)

# 输出结果的精确率、召回率、F1值
report=classification_report(y_test,result,labels=[0,1],target_names=['良性肿瘤','恶性肿瘤'])
print(report)
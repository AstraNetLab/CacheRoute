import numpy as np
import matplotlib.pyplot as plt

# 参数设置
a = 2
b = 3

# 垂直渐近线位置
x0 = -b / a

# 定义 x 轴范围，避开渐近线
x_left = np.linspace(x0 - 5, x0 - 0.1, 400)
x_right = np.linspace(x0 + 0.1, x0 + 5, 400)

# 定义函数
def f(x):
    return (a * x) / (a * x + b)

# 绘图
plt.figure(figsize=(8, 5))

plt.plot(x_left, f(x_left))
plt.plot(x_right, f(x_right))

# 绘制水平渐近线 y = 1
plt.axhline(1, linestyle="--")

# 绘制垂直渐近线 x = -b/a
plt.axvline(x0, linestyle="--")

plt.xlabel("x")
plt.ylabel("f(x)")
plt.title("Function: ax / (ax + b)")

plt.grid(True)
plt.show()

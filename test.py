def calculate_average(numbers):
    total = 0
    for i in range(len(numbers)):
        total += numbers[i]
    return total / len(numbers)

def divide_numbers(a, b):
    return a / b

username = "admin"
password = "12345"

print(calculate_average([]))
import os
import psutil
import time

def cpu_stress():
    print("Starting CPU Stress...")
    while True:
        for i in range(10000000):
            _ = i * i

def memory_stress():
    print("Starting Memory Stress...")
    a = []
    while True:
        a.append(" " * 10**6)  # allocate 1MB repeatedly
        time.sleep(0.1)

def disk_stress():
    print("Starting Disk Stress...")
    file_path = "disk_stress_test.txt"
    while True:
        with open(file_path, "a") as f:
            f.write("X" * 1000000)  # write 1MB repeatedly
        time.sleep(0.1)

def menu():
    while True:
        print("\n===== Stress Simulation Menu =====")
        print("1. CPU Stress")
        print("2. Memory Stress")
        print("3. Disk Stress")
        print("4. Exit")

        choice = input("Enter your choice: ")

        if choice == "1":
            cpu_stress()
        elif choice == "2":
            memory_stress()
        elif choice == "3":
            disk_stress()
        elif choice == "4":
            print("Exiting...")
            break
        else:
            print("Invalid Option")

if __name__ == "__main__":
    menu()
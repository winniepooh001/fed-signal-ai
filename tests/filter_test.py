
from FedTools import MonetaryPolicyCommittee

dataset = MonetaryPolicyCommittee().find_statements()
print(dataset.columns)
print(dataset.head(10))
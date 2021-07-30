import os, sys
import numpy as np
import pandas as pd
from tqdm import tqdm

# random split
def create_fold(df, fold_seed, frac):
	train_frac, val_frac, test_frac = frac
	test = df.sample(frac = test_frac, replace = False, random_state = fold_seed)
	train_val = df[~df.index.isin(test.index)]
	val = train_val.sample(frac = val_frac/(1-test_frac), replace = False, random_state = 1)
	train = train_val[~train_val.index.isin(val.index)]

	return {'train': train.reset_index(drop = True),
			'valid': val.reset_index(drop = True),
			'test': test.reset_index(drop = True)}

# cold setting
def create_fold_setting_cold(df, fold_seed, frac, entity):
	train_frac, val_frac, test_frac = frac
	gene_drop = df[entity].drop_duplicates().sample(frac = test_frac, replace = False, random_state = fold_seed).values

	test = df[df[entity].isin(gene_drop)]

	train_val = df[~df[entity].isin(gene_drop)]

	gene_drop_val = train_val[entity].drop_duplicates().sample(frac = val_frac/(1-test_frac), replace = False, random_state = fold_seed).values
	val = train_val[train_val[entity].isin(gene_drop_val)]
	train = train_val[~train_val[entity].isin(gene_drop_val)]

	return {'train': train.reset_index(drop = True),
			'valid': val.reset_index(drop = True),
			'test': test.reset_index(drop = True)}

# scaffold split
def create_scaffold_split(df, seed, frac, entity):
	# reference: https://github.com/chemprop/chemprop/blob/master/chemprop/data/scaffold.py
	try:
		from rdkit import Chem
		from rdkit.Chem.Scaffolds import MurckoScaffold
		from rdkit import RDLogger
		RDLogger.DisableLog('rdApp.*')
	except:
		raise ImportError("Please install rdkit by 'conda install -c conda-forge rdkit'! ")
	from tqdm import tqdm
	from random import Random

	from collections import defaultdict
	random = Random(seed)

	s = df[entity].values
	scaffolds = defaultdict(set)
	idx2mol = dict(zip(list(range(len(s))),s))

	error_smiles = 0
	for i, smiles in tqdm(enumerate(s), total=len(s)):
		try:
			scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol = Chem.MolFromSmiles(smiles), includeChirality = False)
			scaffolds[scaffold].add(i)
		except:
			print_sys(smiles + ' returns RDKit error and is thus omitted...')
			error_smiles += 1

	train, val, test = [], [], []
	train_size = int((len(df) - error_smiles) * frac[0])
	val_size = int((len(df) - error_smiles) * frac[1])
	test_size = (len(df) - error_smiles) - train_size - val_size
	train_scaffold_count, val_scaffold_count, test_scaffold_count = 0, 0, 0

	#index_sets = sorted(list(scaffolds.values()), key=lambda i: len(i), reverse=True)
	index_sets = list(scaffolds.values())
	big_index_sets = []
	small_index_sets = []
	for index_set in index_sets:
		if len(index_set) > val_size / 2 or len(index_set) > test_size / 2:
			big_index_sets.append(index_set)
		else:
			small_index_sets.append(index_set)
	random.seed(seed)
	random.shuffle(big_index_sets)
	random.shuffle(small_index_sets)
	index_sets = big_index_sets + small_index_sets

	if frac[2] == 0:
		for index_set in index_sets:
			if len(train) + len(index_set) <= train_size:
				train += index_set
				train_scaffold_count += 1
			else:
				val += index_set
				val_scaffold_count += 1
	else:
		for index_set in index_sets:
			if len(train) + len(index_set) <= train_size:
				train += index_set
				train_scaffold_count += 1
			elif len(val) + len(index_set) <= val_size:
				val += index_set
				val_scaffold_count += 1
			else:
				test += index_set
				test_scaffold_count += 1

	return {'train': df.iloc[train].reset_index(drop = True),
			'valid': df.iloc[val].reset_index(drop = True),
			'test': df.iloc[test].reset_index(drop = True)}

def create_combination_split(df, seed, frac):
	"""
	Function for splitting drug combination dataset such that no
	combinations are shared across the split

	:param df: dataset to split as pd Dataframe
	:param seed: random seed
	:param frac: [train, val, test] split fraction as a list
	:return: dictionary of {train, valid, test} datasets
	"""

	# Set split size
	test_size = int(len(df) * frac[2])
	train_size = int(len(df) * frac[0])
	val_size = len(df) - train_size - test_size
	np.random.seed(seed)

	# Create a new column for combination names
	df['concat'] = df['Drug1_ID'] + ',' + df['Drug2_ID']

	# Identify shared drug combinations across all target classes
	combinations = []
	for c in df['Cell_Line_ID'].unique():
		df_cell = df[df['Cell_Line_ID'] == c]
		combinations.append(set(df_cell['concat'].values))

	intxn = combinations[0]
	for c in combinations:
		intxn = intxn.intersection(c)

	# Split combinations into train, val and test
	test_choices = np.random.choice(list(intxn),
						int(test_size / len(df['Cell_Line_ID'].unique())),
						replace=False)
	trainval_intxn = intxn.difference(test_choices)
	val_choices = np.random.choice(list(trainval_intxn),
						int(val_size / len(df['Cell_Line_ID'].unique())),
						replace=False)

	## Create train and test set
	test_set = df[df['concat'].isin(test_choices)].drop(columns=['concat'])
	val_set = df[df['concat'].isin(val_choices)]
	train_set = df[~df['concat'].isin(test_choices)].reset_index(drop=True)
	train_set = train_set[~train_set['concat'].isin(val_choices)]

	return {'train': train_set.reset_index(drop = True),
			'valid': val_set.reset_index(drop = True),
			'test': test_set.reset_index(drop = True)}

# create time split

def create_fold_time(df, frac, date_column):
	df = df.sort_values(by = date_column).reset_index(drop = True)
	train_frac, val_frac, test_frac = frac[0], frac[1], frac[2]

	split_date = df[:int(len(df) * (train_frac + val_frac))].iloc[-1][date_column]
	test = df[df[date_column] >= split_date].reset_index(drop = True)
	train_val = df[df[date_column] < split_date]

	split_date_valid = train_val[:int(len(train_val) * train_frac/(train_frac + val_frac))].iloc[-1][date_column]
	train = train_val[train_val[date_column] <= split_date_valid].reset_index(drop = True)
	valid = train_val[train_val[date_column] > split_date_valid].reset_index(drop = True)

	return {'train': train, 'valid': valid, 'test': test, 'split_time': {'train_time_frame': (df.iloc[0][date_column], split_date_valid), 
                                                                         'valid_time_frame': (split_date_valid, split_date), 
                                                                         'test_time_frame': (split_date, df.iloc[-1][date_column])}}

# split within each stratification defined by the group column

def create_group_split(train_val, seed, holdout_frac, group_column):
	train_df = pd.DataFrame()
	val_df = pd.DataFrame()

	for i in train_val[group_column].unique():
		train_val_temp = train_val[train_val[group_column] == i]
		np.random.seed(seed)
		msk = np.random.rand(len(train_val_temp)) < (1 - holdout_frac)
		train_df = train_df.append(train_val_temp[msk])
		val_df = val_df.append(train_val_temp[~msk])

	return {'train': train_df.reset_index(drop = True), 'valid': val_df.reset_index(drop = True)}
	
def train_val_test_split(len_data, frac, seed):
	test_size = int(len_data * frac[2])
	train_size = int(len_data * frac[0])
	val_size = len_data - train_size - test_size
	np.random.seed(seed)
	x = np.array(list(range(len_data)))
	np.random.shuffle(x)
	return x[:train_size], x[train_size:(train_size + val_size)], x[-test_size:]
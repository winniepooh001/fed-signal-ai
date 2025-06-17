from deap import base, creator, tools, algorithms
import numpy as np
import random
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class GAOptimizer:
    """DEAP-based Genetic Algorithm for optimizing TradingView filter values"""

    def __init__(self, rl_fitness_learner=None):
        self.rl_fitness = rl_fitness_learner
        self.population_size = 30
        self.generations = 15
        self.target_stock_count = 15  # Target 10-20 stocks
        self.crossover_prob = 0.7
        self.mutation_prob = 0.2
        self.tournament_size = 3

        # Realistic parameter ranges for each filter
        self.filter_ranges = {
            'pe_ratio': (3.0, 40.0),
            'debt_to_equity': (0.0, 3.0),
            'dividend_yield': (0.0, 0.12),
            'rsi': (10.0, 90.0),
            'volume_multiplier': (0.5, 10.0),
            'market_cap': (50_000_000, 500_000_000_000),
            'eps_growth': (-0.20, 1.0),
            'revenue_growth': (-0.10, 0.50),
            'roe': (-0.50, 1.0),
            'price_to_book': (0.1, 15.0),
            'current_ratio': (0.5, 10.0),
            'profit_margin': (-0.30, 0.50),
            'return_on_assets': (-0.20, 0.30),
            'beta': (0.1, 3.0),
            'rsi_14': (10.0, 90.0),
            'relative_volume_10d_calc': (0.5, 5.0),
            'price_52_week_high': (0.3, 1.0),  # Percentage of 52-week high
        }

        # Initialize DEAP
        self._setup_deap()

    def _setup_deap(self):
        """Initialize DEAP creator and toolbox"""

        # Create fitness and individual classes
        if not hasattr(creator, "FitnessMax"):
            creator.create("FitnessMax", base.Fitness, weights=(1.0,))
        if not hasattr(creator, "Individual"):
            creator.create("Individual", dict, fitness=creator.FitnessMax)

        self.toolbox = base.Toolbox()

        # Register functions for GA operations
        self.toolbox.register("individual", self._create_individual)
        self.toolbox.register("population", tools.initRepeat, list, self.toolbox.individual)
        self.toolbox.register("evaluate", self._evaluate_fitness)
        self.toolbox.register("mate", self._crossover)
        self.toolbox.register("mutate", self._mutate)
        self.toolbox.register("select", tools.selTournament, tournsize=self.tournament_size)

    def optimize_filters(self, llm_analysis: Dict[str, Any], tradingview_tool=None) -> Dict[str, Any]:
        """
        Main GA optimization function

        Args:
            llm_analysis: Output from LLM environment analyzer
            tradingview_tool: Tool for testing filter combinations

        Returns:
            Optimization result with best filter values
        """

        self.suggested_filters = llm_analysis['filters']
        self.environment = llm_analysis['environment']
        self.tradingview_tool = tradingview_tool

        logger.info(f"Starting GA optimization for {len(self.suggested_filters)} filters")
        logger.info(f"Target environment: {self.environment}")
        logger.info(f"Suggested filters: {self.suggested_filters}")

        # Create initial population
        population = self.toolbox.population(n=self.population_size)

        # Evaluate initial population
        fitnesses = [self.toolbox.evaluate(ind)[0] for ind in population]
        for ind, fit in zip(population, fitnesses):
            ind.fitness.values = (fit,)

        # Statistics tracking
        stats = tools.Statistics(lambda ind: ind.fitness.values)
        stats.register("avg", np.mean)
        stats.register("max", np.max)
        stats.register("min", np.min)

        hall_of_fame = tools.HallOfFame(1)

        # Evolution loop
        logger.info("Starting evolution...")

        for generation in range(self.generations):
            # Select parents
            offspring = self.toolbox.select(population, len(population))
            offspring = [self.toolbox.clone(ind) for ind in offspring]

            # Apply crossover
            for child1, child2 in zip(offspring[::2], offspring[1::2]):
                if random.random() < self.crossover_prob:
                    self.toolbox.mate(child1, child2)
                    del child1.fitness.values
                    del child2.fitness.values

            # Apply mutation
            for mutant in offspring:
                if random.random() < self.mutation_prob:
                    self.toolbox.mutate(mutant)
                    del mutant.fitness.values

            # Evaluate offspring
            invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
            fitnesses = [self.toolbox.evaluate(ind)[0] for ind in invalid_ind]
            for ind, fit in zip(invalid_ind, fitnesses):
                ind.fitness.values = (fit,)

            # Replace population
            population[:] = offspring

            # Update statistics
            hall_of_fame.update(population)
            record = stats.compile(population)

            logger.info(f"Generation {generation + 1}: "
                        f"Max={record['max']:.3f}, "
                        f"Avg={record['avg']:.3f}, "
                        f"Min={record['min']:.3f}")

        # Return best result
        best_individual = hall_of_fame[0]

        return {
            'filters': self.suggested_filters,
            'values': dict(best_individual),
            'fitness': best_individual.fitness.values[0],
            'environment': self.environment,
            'generation_stats': record,
            'optimization_complete': True,
            'timestamp': datetime.now().isoformat()
        }

    def _create_individual(self) -> creator.Individual:
        """Create a random individual (filter value combination)"""
        individual = creator.Individual()

        for filter_name in self.suggested_filters:
            if filter_name in self.filter_ranges:
                min_val, max_val = self.filter_ranges[filter_name]
                individual[filter_name] = random.uniform(min_val, max_val)
            else:
                logger.warning(f"Unknown filter {filter_name}, using default range")
                individual[filter_name] = random.uniform(0.1, 100.0)

        return individual

    def _evaluate_fitness(self, individual: creator.Individual) -> tuple:
        """
        Evaluate fitness of an individual

        Returns:
            tuple: (fitness_score,)
        """

        # Primary fitness: stock count target
        estimated_count = self._estimate_stock_count(individual)
        count_fitness = self._calculate_count_fitness(estimated_count)
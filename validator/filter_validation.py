from typing import List, Dict, Any
from collections import defaultdict
from utils.logging_config import get_logger

logger = get_logger()


class FilterValidator:
    """Validates and auto-fixes common filter issues"""

    @staticmethod
    def validate_and_fix_filters(filters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validates filters and automatically fixes common issues:
        1. Converts multiple equals filters for same column to 'in' filter
        2. Converts separate greater_than + less_than to range filter
        3. Removes duplicate filters

        Args:
            filters: List of filter dictionaries

        Returns:
            Fixed list of filter dictionaries
        """

        logger.debug(f"Validating {len(filters)} filters")

        # Group filters by column
        column_groups = defaultdict(list)
        standalone_filters = []

        for filter_dict in filters:
            if 'column' in filter_dict and filter_dict['column']:
                column_groups[filter_dict['column']].append(filter_dict)
            else:
                standalone_filters.append(filter_dict)

        fixed_filters = standalone_filters.copy()

        # Process each column group
        for column, column_filters in column_groups.items():
            if len(column_filters) == 1:
                # Single filter for this column - keep as is
                fixed_filters.extend(column_filters)
            else:
                # Multiple filters for same column - needs fixing
                logger.info(f"Fixing {len(column_filters)} filters for column '{column}'")
                fixed_filter = FilterValidator._fix_column_filters(column, column_filters)
                if fixed_filter:
                    if isinstance(fixed_filter, list):
                        fixed_filters.extend(fixed_filter)
                    else:
                        fixed_filters.append(fixed_filter)

        logger.info(f"Filter validation: {len(filters)} → {len(fixed_filters)} filters")
        return fixed_filters

    @staticmethod
    def _fix_column_filters(column: str, filters: List[Dict[str, Any]]) -> Dict[str, Any] or List[Dict[str, Any]]:
        """Fix multiple filters for the same column"""

        filter_types = [f.get('type') for f in filters]

        # Case 1: Multiple equals filters → Convert to 'in' filter
        if all(ftype == 'equals' for ftype in filter_types):
            values = [f.get('value') for f in filters if f.get('value') is not None]
            logger.info(f"Converting {len(filters)} equals filters to 'in' filter for {column}: {values}")
            return {
                'type': 'in',
                'column': column,
                'values': values
            }

        # Case 2: Greater than + Less than → Convert to range filter
        elif set(filter_types) == {'greater_than', 'less_than'}:
            gt_filter = next(f for f in filters if f.get('type') == 'greater_than')
            lt_filter = next(f for f in filters if f.get('type') == 'less_than')

            min_val = gt_filter.get('value')
            max_val = lt_filter.get('value')

            logger.info(f"Converting greater_than + less_than to range filter for {column}: {min_val}-{max_val}")
            return {
                'type': 'range',
                'column': column,
                'min_value': min_val,
                'max_value': max_val
            }

        # Case 3: Mix of 'in' with other types → Keep 'in', remove others
        elif 'in' in filter_types:
            in_filter = next(f for f in filters if f.get('type') == 'in')
            logger.warning(f"Found 'in' filter mixed with others for {column} - keeping only 'in' filter")
            return in_filter

        # Case 4: Multiple range filters → Use the most restrictive one
        elif all(ftype == 'range' for ftype in filter_types):
            # Find the most restrictive range (highest min, lowest max)
            best_filter = filters[0]
            for f in filters[1:]:
                if (f.get('min_value', 0) > best_filter.get('min_value', 0) or
                        f.get('max_value', float('inf')) < best_filter.get('max_value', float('inf'))):
                    best_filter = f

            logger.info(f"Multiple range filters for {column} - using most restrictive: "
                        f"{best_filter.get('min_value')}-{best_filter.get('max_value')}")
            return best_filter

        # Case 5: Complex mix → Try to be smart about it
        else:
            logger.warning(f"Complex filter mix for {column}: {filter_types} - applying heuristics")

            # Prefer specific filters over general ones
            priority_order = ['range', 'in', 'equals', 'greater_than', 'less_than']

            for preferred_type in priority_order:
                matching_filters = [f for f in filters if f.get('type') == preferred_type]
                if matching_filters:
                    logger.info(f"Selecting {preferred_type} filter for {column}")
                    return matching_filters[0]  # Use first one of preferred type

            # Fallback - use first filter
            logger.warning(f"Using first filter as fallback for {column}")
            return filters[0]

import asyncio

from scripts.fast_shell import UserORMModel, select, session


async def main():
    result = await session.execute(select(UserORMModel))
    users = result.scalars().all()

    if users:
        print(f'Found {len(users)} user(s):')
        print('-' * 80)
        for user in users:
            print(
                f'{user.id}, '
                f'{user.username}, '
                f'{user.email}, '
                f'{user.role}, '
                f'{user.status}'
            )
    else:
        print('No users found in the database.')


asyncio.run(main())

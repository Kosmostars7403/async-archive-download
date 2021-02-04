import argparse
import os
import asyncio
import logging
from datetime import datetime

from aiohttp import web
import aiofiles
from environs import Env


CHUNK_SIZE_IN_KB = 500
DEFAULT_IMAGE_FOLDER = 'test_photos'


async def archivate(request):
    hash = request.match_info.get('archive_hash', '')

    if not os.path.exists(f'{images_root_folder}/{hash}'):
        raise web.HTTPNotFound(text='Архив не существует или был удален')

    response = web.StreamResponse()
    response.headers['Content-Disposition'] = f'attachment; filename="{hash}.zip"'

    await response.prepare(request)

    process = await asyncio.create_subprocess_exec(
        'zip', '-', hash, '-r',
        stdout=asyncio.subprocess.PIPE,
        cwd=images_root_folder
    )

    try:
        while True:
            logging.info(f'[{datetime.now()}] Sending archive chunk ...')
            archive = await process.stdout.read(CHUNK_SIZE_IN_KB * 1024)
            await response.write(archive)
            await asyncio.sleep(latency)

            if process.stdout.at_eof():
                break

    except asyncio.CancelledError:
        logging.error(f'[{datetime.now()}] Download was interrupted')
    finally:
        process.kill()
        await process.wait()
        response.force_close()

    return response


async def handle_index_page(request):
    async with aiofiles.open('index.html', mode='r') as index_file:
        index_contents = await index_file.read()
    return web.Response(text=index_contents, content_type='text/html')


def get_service_settings():
    env = Env()
    env.read_env()
    parser = argparse.ArgumentParser()

    parser.add_argument('--latency', help='Set latency between archive chunks.', default=0, type=float)
    parser.add_argument('--logging', help='Enable logging process information.', action='store_true')
    parser.add_argument('--image_path', help='Change default photos folder path.', default=None)

    args = parser.parse_args()

    (args.logging or env.bool('LOGGING', False)) and logging.basicConfig(level=logging.DEBUG)
    latency = args.latency or float(env('LATENCY', 0.0))
    images_root_folder = args.image_path or env('PHOTOS_ROOT_FOLDER', DEFAULT_IMAGE_FOLDER)

    return latency, images_root_folder


if __name__ == '__main__':
    latency, images_root_folder = get_service_settings()

    app = web.Application()
    app.add_routes([
        web.get('/', handle_index_page),
        web.get('/archive/{archive_hash}/', archivate),
    ])
    web.run_app(app)

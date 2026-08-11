        elif action == "aud":
            ydl_opts = {
                'format': 'bestaudio',
                'outtmpl': '%(id)s.%(ext)s',
                'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
            }
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)
            if file_path and os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    bot.send_audio(
                        call.message.chat.id, 
                        f, 
                        performer=BOT_USERNAME, 
                        title=info.get('title', 'Audio'), 
                        caption=f"• {BOT_USERNAME}"
                    )
                
        elif action == "voi":
            ydl_opts = {
                'format': 'bestaudio',
                'outtmpl': '%(id)s.%(ext)s',
                'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
            }
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)
            if file_path and os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    bot.send_voice(call.message.chat.id, f, caption=f"• {BOT_USERNAME}")
